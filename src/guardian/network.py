"""GET-only transport: validate DNS, then connect to the validated IP with host TLS."""
import http.client
import ipaddress
import os
import socket
import ssl
import time
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlsplit

from .models import SiteConfig


class PolicyError(ValueError):
    pass


def enabled():
    if Path(os.getenv("GUARDIAN_STOP_FILE", "data/STOP")).exists():
        raise PolicyError("Agent disabled by kill switch file")
    if os.getenv("AGENT_ENABLED", "true").lower() != "true":
        raise PolicyError("Agent disabled by kill switch")


def validate_url(url: str, config: SiteConfig):
    p = urlsplit(url)
    if (p.scheme != "https" or p.hostname not in config.allowed_hosts
            or p.username or p.password or p.port not in (None, 443)
            or p.query or p.fragment or p.path not in config.allowed_paths):
        raise PolicyError("URL outside approved HTTPS hosts/routes")
    return p


def public_addresses(host: str):
    addresses = list(dict.fromkeys(x[4][0] for x in socket.getaddrinfo(
        host, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise PolicyError("DNS includes a non-public address")
    return addresses


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes
    truncated: bool = False


class Transport:
    def __init__(self, config):
        self.config = config
        self.requests = 0

    def connection(self, url):
        enabled()
        p = validate_url(url, self.config)
        address = public_addresses(p.hostname)[0]
        return PinnedHTTPS(p.hostname, address, self.config.timeout)

    def get(self, url):
        enabled()
        if self.requests >= self.config.max_requests:
            raise PolicyError("Request budget exhausted")
        self.requests += 1
        time.sleep(self.config.delay)
        c = self.connection(url)
        deadline = time.monotonic() + self.config.timeout
        try:
            c.request("GET", urlsplit(url).path, headers={
                "User-Agent": "WebsiteGuardian/0.1 (owner-authorized read-only audit)",
                "Accept-Encoding": "identity", "Accept": "text/html,application/json"})
            r = c.getresponse()
            chunks = bytearray()
            while len(chunks) <= self.config.max_bytes:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Response deadline exceeded")
                if c.sock:
                    c.sock.settimeout(remaining)
                chunk = r.read1(min(16384, self.config.max_bytes + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
            return Response(r.status, {k.lower(): v for k, v in r.getheaders()},
                            bytes(chunks[:self.config.max_bytes]), len(chunks) > self.config.max_bytes)
        finally:
            c.close()

    def certificate(self, url):
        c = self.connection(url)
        try:
            c.connect()
            return c.sock.getpeercert()
        finally:
            c.close()
