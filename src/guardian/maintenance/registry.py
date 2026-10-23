"""Bounded public registry reads; never executes package metadata or release prose."""
import json
import httpx
from urllib.parse import quote
from guardian.maintenance.policy import PACKAGE


def metadata(name, client=None):
    if not PACKAGE.fullmatch(name):
        raise ValueError('Invalid registry package')
    own = client is None
    client = client or httpx.Client(trust_env=False, follow_redirects=False, timeout=30)
    try:
        with client.stream('GET', 'https://registry.npmjs.org/' + quote(name, safe='@')) as response:
            response.raise_for_status()
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > 64 * 1024 * 1024:
                    raise ValueError('Registry metadata exceeds budget')
        result = json.loads(raw)
        if result.get('name') != name or not isinstance(result.get('versions'), dict) or not isinstance(result.get('time'), dict):
            raise ValueError('Incomplete registry evidence')
        return result
    finally:
        if own:
            client.close()
