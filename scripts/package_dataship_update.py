"""Create a signed update ZIP from a clean Windows build and an Ed25519 key."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.dataship_update_package import DATA_SCHEMA, MANIFEST, REQUIRED, SIGNATURE, TARGET, payload_path, version_key


def package(app: Path, output: Path, version: str, key: Ed25519PrivateKey) -> None:
    version_key(version)
    files = sorted((*REQUIRED, *(p.relative_to(app).as_posix() for p in (app / '_internal').rglob('*') if p.is_file())))
    if not any(path.startswith('_internal/') for path in files):
        raise ValueError('Windows build is missing _internal.')
    digests = {}
    for name in files:
        payload_path(name)
        with (app / name).open('rb') as stream:
            digests[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    manifest = json.dumps({'format': 1, 'target': TARGET, 'version': version,
                           'data_schema': DATA_SCHEMA, 'files': digests}, sort_keys=True).encode('utf-8')
    with ZipFile(output, 'x', compression=ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, manifest)
        archive.writestr(SIGNATURE, key.sign(manifest))
        for name in files:
            archive.write(app / name, name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--key', required=True, type=Path)
    args = parser.parse_args()
    key = load_pem_private_key(args.key.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        parser.error('Expected an Ed25519 private key.')
    package(args.app, args.output, args.version, key)
