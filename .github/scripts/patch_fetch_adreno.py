#!/usr/bin/env python3
"""Authenticate fetch-adreno-inputs.py: it calls api.github.com without a token."""
import io
import os
import pathlib
import sys

targets = [pathlib.Path('device/scripts/fetch-adreno-inputs.py'),
           pathlib.Path('out/fuxi/tree/scripts/fetch-adreno-inputs.py')]

OLD = "    request = urllib.request.Request(url, headers={'User-Agent': 'sheng-offline-adreno-audit'})"
NEW = ("    _headers = {'User-Agent': 'sheng-offline-adreno-audit'}\n"
       "    _token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')\n"
       "    if _token and 'api.github.com' in url:\n"
       "        _headers['Authorization'] = 'Bearer ' + _token  # CI authentication\n"
       "    request = urllib.request.Request(url, headers=_headers)")

patched = []
for p in targets:
    if not p.is_file():
        continue
    s = io.open(p, encoding='utf-8').read()
    if 'CI authentication' in s:
        continue
    if OLD not in s:
        print('pattern not found in', p)
        continue
    s = s.replace(OLD, NEW, 1)
    if 'import os' not in s:
        s = s.replace('import urllib.request', 'import os\nimport urllib.request', 1)
    io.open(p, 'w', encoding='utf-8').write(s)
    patched.append(str(p))
print('fetch-adreno patched:', patched)