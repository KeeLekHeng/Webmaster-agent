"""Scoped repository access. Repository content is data and is never executed."""
import base64
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath

import httpx
from pydantic import BaseModel, Field, model_validator

from .network import PolicyError, enabled


MAX_FILE = 262144


def safe_path(path):
    p = PurePosixPath(path)
    reserved = {"con", "prn", "aux", "nul"} | {f"{prefix}{i}" for prefix in ("com", "lpt") for i in range(1, 10)}
    if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./-]*", path) or p.is_absolute()
            or any(part.lower() in ("", ".", "..", ".git", ".github") or part.lower().startswith(".env")
                   or part.split(".")[0].lower() in reserved or part.endswith(".") for part in path.split("/"))):
        raise PolicyError("Repository path is outside permitted file scope")
    return path


def sha(value):
    return hashlib.sha256(value).hexdigest()


def blob_sha(value):
    return hashlib.sha1(b"blob " + str(len(value)).encode() + b"\0" + value).hexdigest()


class RepoConfig(BaseModel):
    model_config = {"extra": "forbid"}
    owner: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
    base_branch: str = Field(default="main", pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
    read_paths: list[str]
    patch_paths: list[str]
    allow_pr_creation: bool = False
    approver_ids: list[str] = []

    @model_validator(mode="after")
    def paths(self):
        for path in self.read_paths + self.patch_paths:
            safe_path(path)
        if not set(self.patch_paths) <= set(self.read_paths):
            raise ValueError("Patch paths must also be readable")
        return self


class LocalRepository:
    def __init__(self, path, config):
        self.path = Path(path).resolve(strict=True)
        self.config = config
        self.git = shutil.which("git")
        if not self.git:
            raise ValueError("Git executable unavailable")

    def _git(self, *args):
        enabled()
        result = subprocess.run([self.git, "--no-pager", "-c", "core.fsmonitor=false",
            "-c", "core.hooksPath=", "-c", "core.pager=cat", "-C", str(self.path), *args],
            shell=False, capture_output=True, timeout=15)
        if result.returncode or len(result.stdout) > MAX_FILE:
            raise PolicyError("Read-only repository operation failed or exceeded size limit")
        return result.stdout

    def revision(self):
        revision = self._git("rev-parse", "--verify", "HEAD^{commit}").decode().strip()
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise PolicyError("Unsupported repository revision")
        return revision

    def read(self, path, revision):
        safe_path(path)
        if path not in self.config.read_paths or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise PolicyError("Repository file/revision not approved")
        listing = self._git("ls-tree", revision, "--", path).decode().split()
        if len(listing) != 4 or listing[0] != "100644" or listing[1] != "blob":
            raise PolicyError("Only regular non-executable tracked files can be read")
        if int(self._git("cat-file", "-s", f"{revision}:{path}")) > MAX_FILE:
            raise PolicyError("Repository source file exceeds limit")
        return self._git("show", f"{revision}:{path}")


class GitHubRepository:
    def __init__(self, config, token, client=None):
        if not token:
            raise PolicyError("A separately configured GitHub token is required")
        self.config = config
        self.token = token
        self.client = client
        self.prefix = f"/repos/{config.owner}/{config.name}"

    def _request(self, method, suffix, **kwargs):
        enabled()
        client = self.client or httpx.Client(timeout=15, trust_env=False, follow_redirects=False)
        try:
            with client.stream(method, "https://api.github.com" + self.prefix + suffix,
                    headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                             "X-GitHub-Api-Version": "2026-03-10"}, **kwargs) as response:
                if not 200 <= response.status_code < 300:
                    raise PolicyError(f"GitHub request failed (HTTP {response.status_code}); response body omitted")
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 1048576:
                        raise PolicyError("GitHub response exceeded size limit")
                import json
                return json.loads(data)
        finally:
            if self.client is None:
                client.close()

    def branch(self):
        data = self._request("GET", f"/branches/{self.config.base_branch}")
        revision = data["commit"]["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise PolicyError("Invalid GitHub branch revision")
        return revision, data.get("protected") is True

    def revision(self):
        return self.branch()[0]

    def read(self, path, revision):
        safe_path(path)
        if path not in self.config.read_paths or not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise PolicyError("Repository file/revision not approved")
        tree = revision
        parts = path.split("/")
        expected_blob = None
        for index, part in enumerate(parts):
            entries = self._request("GET", f"/git/trees/{tree}")
            if entries.get("truncated"):
                raise PolicyError("Incomplete repository tree")
            matches = [e for e in entries.get("tree", []) if e.get("path") == part]
            if len(matches) != 1:
                raise PolicyError("Repository path missing from pinned tree")
            entry = matches[0]
            if not re.fullmatch(r"[0-9a-f]{40}", entry.get("sha", "")):
                raise PolicyError("Invalid repository tree object ID")
            if index < len(parts)-1:
                if entry.get("mode") != "040000" or entry.get("type") != "tree":
                    raise PolicyError("Repository path is not a regular directory")
                tree = entry["sha"]
            elif entry.get("mode") == "100644" and entry.get("type") == "blob":
                expected_blob = entry["sha"]
            else:
                raise PolicyError("Repository content must be a regular non-executable file")
        data = self._request("GET", f"/contents/{path}", params={"ref": revision})
        if data.get("type") != "file" or data.get("encoding") != "base64" or data.get("size", MAX_FILE+1) > MAX_FILE:
            raise PolicyError("Unsupported repository content")
        content = base64.b64decode("".join(data["content"].split()), validate=True)
        if len(content) > MAX_FILE or blob_sha(content) != data.get("sha") or data.get("sha") != expected_blob:
            raise PolicyError("Repository content hash mismatch")
        return content
