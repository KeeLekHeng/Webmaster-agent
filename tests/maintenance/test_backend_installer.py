"""Pin and archive handling boundaries, without downloading or executing a CLI."""
import hashlib
import importlib.util
import io
import tarfile
from pathlib import Path

import pytest


@pytest.fixture
def installer(monkeypatch):
    spec=importlib.util.spec_from_file_location('backend_installer',Path('maintenance/install-backend-cli.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module.platform,'system',lambda:'Linux')
    monkeypatch.setattr(module.platform,'machine',lambda:'x86_64')
    return module


def archive(kind='regular'):
    output=io.BytesIO()
    with tarfile.open(fileobj=output,mode='w:gz') as handle:
        info=tarfile.TarInfo('supabase')
        if kind=='link':info.type=tarfile.SYMTYPE;info.linkname='/tmp/elsewhere'
        else:info.size=4
        handle.addfile(info,None if kind=='link' else io.BytesIO(b'test'))
        # A second archive member must never be extracted.
        other=tarfile.TarInfo('../untrusted');other.size=4
        handle.addfile(other,io.BytesIO(b'data'))
    return output.getvalue()


def download(module,monkeypatch,raw,*,valid=True):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def raise_for_status(self):pass
        def iter_bytes(self):yield raw
        def stream(self,*args):return self
    monkeypatch.setattr(module.httpx,'Client',lambda **kwargs:Response())
    monkeypatch.setattr(module,'SHA256',hashlib.sha256(raw).hexdigest() if valid else '0'*64)


def test_verified_archive_extracts_only_named_binary(installer,monkeypatch,tmp_path):
    download(installer,monkeypatch,archive())
    target=installer.install(tmp_path/'cli')
    assert target.read_bytes()==b'test'
    assert not (tmp_path/'untrusted').exists()


def test_checksum_failure_creates_no_binary(installer,monkeypatch,tmp_path):
    download(installer,monkeypatch,archive(),valid=False)
    with pytest.raises(ValueError,match='checksum'):installer.install(tmp_path/'cli')
    assert not (tmp_path/'cli').exists()


def test_archive_symlink_is_rejected(installer,monkeypatch,tmp_path):
    download(installer,monkeypatch,archive('link'))
    with pytest.raises(ValueError,match='member'):installer.install(tmp_path/'cli')
    assert not (tmp_path/'cli'/'supabase').exists()


def test_existing_binary_is_preserved(installer,monkeypatch,tmp_path):
    download(installer,monkeypatch,archive())
    (tmp_path/'supabase').write_bytes(b'keep')
    with pytest.raises(ValueError,match='fresh'):installer.install(tmp_path)
    assert (tmp_path/'supabase').read_bytes()==b'keep'
