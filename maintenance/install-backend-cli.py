"""Install the reviewed Linux CI binary; never use a project package script."""
import argparse
import hashlib
import io
import os
import platform
import tarfile
from pathlib import Path
import httpx

VERSION = '2.119.0'
SHA256 = 'bf1c3ae93be98533eb8a3105dbf4564bd0b2d9dc24690d8a920f980ef975c1b4'
URL = f'https://github.com/supabase/cli/releases/download/v{VERSION}/supabase_linux_amd64.tar.gz'


def install(directory):
    if platform.system()!='Linux' or platform.machine() not in {'x86_64','AMD64'}:
        raise ValueError('Reviewed backend installer supports Linux amd64 CI only')
    with httpx.Client(trust_env=False, follow_redirects=True, timeout=60) as client:
        with client.stream('GET',URL) as response:
            response.raise_for_status()
            raw=bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw)>100*1024*1024:raise ValueError('CLI archive budget exceeded')
    if hashlib.sha256(raw).hexdigest()!=SHA256:raise ValueError('CLI archive checksum mismatch')
    directory=Path(directory).resolve();directory.mkdir(parents=True,exist_ok=True)
    target=directory/'supabase'
    if target.exists() or target.is_symlink():raise ValueError('CLI destination must be fresh')
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        members=[m for m in archive.getmembers() if m.name in {'supabase','./supabase'}]
        if len(members)!=1 or not members[0].isfile() or members[0].size>200*1024*1024:
            raise ValueError('Unexpected CLI archive member')
        with target.open('xb') as output:
            output.write(archive.extractfile(members[0]).read())
    target.chmod(0o700)
    return target


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True)
    path=install(parser.parse_args().directory)
    print(f'Installed reviewed Supabase CLI {VERSION}')
    if os.getenv('GITHUB_PATH'):
        with open(os.environ['GITHUB_PATH'],'a') as output:output.write(str(path.parent)+'\n')
