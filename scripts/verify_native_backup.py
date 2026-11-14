"""Verify all files in a project native backup before any restoration."""
import hashlib
import json
from pathlib import Path
import sys

folder=Path(sys.argv[1]).resolve()
manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
for name,digest in manifest.items():
    file=(folder/name).resolve()
    if not file.is_relative_to(folder): raise SystemExit('Manifest path outside backup refused')
    if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest()!=digest:
        raise SystemExit(f'FAIL: backup file missing or altered: {name}')
print(f'PASS: {len(manifest)} backup files match the SHA256 manifest')
