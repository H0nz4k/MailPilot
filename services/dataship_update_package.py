"""Signed, offline-verifiable update packages for the Windows x64 build."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import stat
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MANIFEST = 'manifest.json'
SIGNATURE = 'manifest.sig'
TARGET = 'dataship-windows-x64'
DATA_SCHEMA = 1
REQUIRED = {'DataShip.exe', 'DataShip-Worker.exe'}
MAX_EXPANDED = 1024 ** 3
MAX_MANIFEST = 4 * 1024 ** 2
COMPONENT = re.compile(r'[A-Za-z0-9_.+ -]+')
RESERVED = {'CON', 'PRN', 'AUX', 'NUL', *(f'{prefix}{i}' for prefix in ('COM', 'LPT') for i in range(10))}


def version_key(version: str) -> tuple:
    match = re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-rc\.([1-9][0-9]*))?', version)
    if not match:
        raise ValueError('Neplatná verze DataShipu.')
    major, minor, patch, rc = match.groups()
    return int(major), int(minor), int(patch), rc is None, int(rc or 0)


def payload_path(name: str) -> PurePosixPath:
    parts = name.split('/')
    if any(not COMPONENT.fullmatch(part) or part.endswith(('.', ' '))
           or part.split('.')[0].upper() in RESERVED for part in parts):
        raise ValueError('Nepovolená cesta v aktualizaci.')
    if name not in REQUIRED and not (len(parts) > 1 and parts[0] == '_internal'):
        raise ValueError('Balíček obsahuje cestu mimo programové soubory.')
    return PurePosixPath(name)


def _unique_object(pairs):
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError('Manifest obsahuje duplicitní klíč.')
    return result


def stage_package(archive: Path, destination: Path, public_key: bytes, installed: str) -> str:
    """Expand only authenticated program files into a new private staging directory."""
    if archive.stat().st_size > MAX_EXPANDED:
        raise ValueError('Aktualizační ZIP překračuje limit velikosti.')
    with ZipFile(archive) as package:
        entries = package.infolist()
        names = [item.filename.casefold() for item in entries]
        if len(set(names)) != len(names) or sum(item.file_size for item in entries) > MAX_EXPANDED:
            raise ValueError('Balíček obsahuje duplicitní soubory nebo překračuje limit velikosti.')
        if package.getinfo(MANIFEST).file_size > MAX_MANIFEST or package.getinfo(SIGNATURE).file_size != 64:
            raise ValueError('Neplatná velikost manifestu nebo podpisu.')
        manifest = package.read(MANIFEST)
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(package.read(SIGNATURE), manifest)
        except InvalidSignature as exc:
            raise ValueError('Podpis aktualizace se nepodařilo ověřit.') from exc
        metadata = json.loads(manifest, object_pairs_hook=_unique_object)
        if (not isinstance(metadata, dict) or metadata.get('format') != 1
                or metadata.get('target') != TARGET or metadata.get('data_schema') != DATA_SCHEMA):
            raise ValueError('Balíček není kompatibilní s touto instalací.')
        version, files = metadata.get('version'), metadata.get('files')
        if not isinstance(version, str) or version_key(version) <= version_key(installed):
            raise ValueError('Balíček musí obsahovat novější verzi.')
        if not isinstance(files, dict) or not REQUIRED <= files.keys() or not any(
            name.startswith('_internal/') for name in files
        ) or set(files) | {MANIFEST, SIGNATURE} != {entry.filename for entry in entries}:
            raise ValueError('Obsah balíčku neodpovídá manifestu.')
        for name, digest in files.items():
            payload_path(name)
            entry = package.getinfo(name)
            if stat.S_IFMT(entry.external_attr >> 16) not in (0, stat.S_IFREG) or not isinstance(
                digest, str
            ) or not re.fullmatch(r'[a-f0-9]{64}', digest):
                raise ValueError('Balíček obsahuje neplatný soubor nebo kontrolní součet.')
        destination.mkdir()
        try:
            for name, expected in files.items():
                target = destination.joinpath(*payload_path(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with package.open(name) as source, target.open('xb') as output:
                    while chunk := source.read(1024 ** 2):
                        digest.update(chunk)
                        output.write(chunk)
                if digest.hexdigest() != expected:
                    raise ValueError(f'Kontrolní součet souboru {name} nesouhlasí.')
        except BaseException:
            shutil.rmtree(destination)
            raise
    return version
