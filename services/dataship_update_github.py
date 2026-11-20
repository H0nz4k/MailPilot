"""Discover and download the signed update asset through GitHub Releases."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote
from urllib.request import Request, urlopen

from services.dataship_update_package import version_key

REPOSITORY = 'H0nz4k/MailPilot'
MAX_DOWNLOAD = 1024 ** 3


@dataclass(frozen=True)
class Release:
    tag: str
    version: str
    notes: str
    asset_id: int


class GitHubReleases:
    def __init__(self, repository: str = REPOSITORY, *, authenticated: bool = False):
        if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('Neplatný název repozitáře GitHub.')
        self.repository = repository
        self.authenticated = authenticated

    def _get(self, endpoint: str, accept: str, output, maximum: int) -> None:
        if self.authenticated:
            # gh uses the operator's own credentials, never a distributed token.
            executable = shutil.which('gh')
            if not executable:
                raise RuntimeError('Pro přístup k privátnímu repozitáři je nutné přihlášení přes GitHub CLI.')
            result = subprocess.run(
                [executable, 'api', '--hostname', 'github.com', endpoint, '-H', f'Accept: {accept}'],
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL, timeout=600,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            if result.returncode:
                raise RuntimeError('GitHub požadavek selhal. Zkontrolujte přístup GitHub CLI k repozitáři.')
            if output.tell() > maximum:
                raise ValueError('Odpověď GitHubu překračuje limit velikosti.')
            return
        request = Request(f'https://api.github.com/{endpoint}', headers={'Accept': accept})
        with urlopen(request, timeout=30) as response:
            total = 0
            while chunk := response.read(1024 ** 2):
                total += len(chunk)
                if total > maximum:
                    raise ValueError('Odpověď GitHubu překračuje limit velikosti.')
                output.write(chunk)

    def latest(self, installed: str) -> Release | None:
        with tempfile.TemporaryFile() as stream:
            self._get(f'repos/{self.repository}/releases/latest', 'application/vnd.github+json',
                      stream, 4 * 1024 ** 2)
            stream.seek(0)
            release = json.load(stream)
        tag = release['tag_name']
        if release.get('draft') or release.get('prerelease') or not tag.startswith('dataship-v'):
            return None
        version = tag.removeprefix('dataship-v')
        if version_key(version) <= version_key(installed):
            return None
        filename = f'DataShip-{version}-Windows-x64-Update.zip'
        for asset in release['assets']:
            if asset['name'] == filename and type(asset['id']) is int and asset['id'] > 0:
                return Release(tag, version, release.get('body') or '', asset['id'])
        return None

    def download(self, release: Release, destination: Path) -> None:
        endpoint = f'repos/{self.repository}/releases/assets/{quote(str(release.asset_id), safe="")}'
        with destination.open('xb') as stream:
            try:
                self._get(endpoint, 'application/octet-stream', stream, MAX_DOWNLOAD)
            except BaseException:
                stream.close()
                destination.unlink(missing_ok=True)
                raise
