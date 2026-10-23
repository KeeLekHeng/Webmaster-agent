"""Prepare public font fixtures outside the test container; never uses site secrets."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
import httpx

CSS_URL = 'https://fonts.googleapis.com/css2?family=Overpass:wght@100..900&display=swap'


def font_fixture(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=30) as client:
        response = client.get(CSS_URL, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        if len(response.content) > 65536:
            raise ValueError('Font stylesheet exceeds fixture budget')
        css = response.text
        for url in sorted(set(re.findall(r'url\((https://[^)]+)\)', css))):
            parsed = urlsplit(url)
            if parsed.hostname != 'fonts.gstatic.com' or parsed.username or parsed.port or parsed.query:
                raise ValueError('Unknown font host')
            font = client.get(url)
            font.raise_for_status()
            if len(font.content) > 2 * 1024 * 1024:
                raise ValueError('Font exceeds fixture budget')
            suffix = Path(parsed.path).suffix
            if suffix not in {'.woff2', '.woff', '.ttf', '.otf'}:
                raise ValueError('Unknown public font format')
            name = hashlib.sha256(font.content).hexdigest() + suffix
            (directory / name).write_bytes(font.content)
            css = css.replace(url, 'http://127.0.0.1:37913/' + name)
    # Next's explicit Google-font test hook. This fixture never changes SIS source.
    # Turbopack serializes the module into a map: a Proxy with no own keys becomes {}.
    # Unknown font requests must fail rather than silently matching every URL.
    module = 'module.exports=' + json.dumps({CSS_URL: css}) + ';\n'
    (directory / 'fonts.cjs').write_text(module, encoding='utf-8')
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir()}
