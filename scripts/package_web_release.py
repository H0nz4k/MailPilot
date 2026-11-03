"""Create distributable ZIPs from an allowlist, never from saved customer settings."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.web_branding import WEB_VERSION, WEB_BUILD

NSSM_VERSION = '2.24-101-g897c7ad'
NSSM_URL = f'https://nssm.cc/ci/nssm-{NSSM_VERSION}.zip'
NSSM_SHA256 = '99f5045fffbffb745d67fe3a065a953c4a3d9c253b868892d9b685b0ee7d07b8'
# Our rc.3 bundle contains these exact verified upstream NSSM files. Only its
# NSSM payload is reused; no older GUI, worker or configuration is extracted.
NSSM_FALLBACK_ASSET = 'repos/H0nz4k/MailPilot/releases/assets/666037948'
NSSM_FALLBACK_SHA256 = '6cc4eb73e25a8a43d28fbd865918136459db586a48bb52eb1ca50d49d02feaa9'
NSSM_RC8_SHA256 = '0c36e63cea5b8f9f6f96d497c4fc324909a76ab927c7683fafb45d71e1a8243a'
REQUIRED_FILES = ('DataShip.exe', 'DataShip-Worker.exe', 'START_WEB.cmd', 'START_WORKER_MANUAL.cmd')


def verified_nssm(archive: Path) -> bytes:
    data = archive.read_bytes()
    if hashlib.sha256(data).hexdigest() not in (NSSM_SHA256, NSSM_FALLBACK_SHA256, NSSM_RC8_SHA256):
        raise ValueError('NSSM archive checksum does not match the pinned upstream build.')
    return data


def download_nssm_fallback(archive: Path) -> None:
    """Read a pinned asset from our own release with gh's authenticated client."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=archive.parent, prefix='nssm-fallback-', delete=False) as file:
            temporary = Path(file.name)
            try:
                subprocess.run(
                    ['gh', 'api', '--hostname', 'github.com', NSSM_FALLBACK_ASSET,
                     '--header', 'Accept: application/octet-stream'],
                    stdout=file, stderr=subprocess.PIPE, check=True,
                )
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or b'').decode('utf-8', errors='replace').strip()
                raise RuntimeError(f'GitHub NSSM fallback failed: {detail}') from None
        # Require the whole known bundle, even if an API error returned JSON.
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != NSSM_FALLBACK_SHA256:
            raise ValueError('Fallback NSSM bundle checksum does not match the pinned release.')
        temporary.replace(archive)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def download_nssm(archive: Path) -> None:
    """Retry a short upstream outage; cache only a complete, verified archive."""
    archive.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        temporary = None
        try:
            with urllib.request.urlopen(NSSM_URL, timeout=60) as response:
                data = response.read()
            with tempfile.NamedTemporaryFile(dir=archive.parent, prefix='nssm-download-', delete=False) as file:
                temporary = Path(file.name)
                file.write(data)
            verified_nssm(temporary)
            temporary.replace(archive)
            return
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (408, 429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                print('Pouzivam overeny NSSM z naseho predchoziho balicku na GitHubu.')
                download_nssm_fallback(archive)
                return
            print(f'NSSM server je docasne nedostupny. Opakuji stazeni ({attempt + 2}/3)...')
            time.sleep(2 ** attempt)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def make_zip(stage: Path, output: Path) -> None:
    with ZipFile(output, 'w', compression=ZIP_DEFLATED, compresslevel=6) as z:
        for item in sorted(stage.rglob('*')):
            if item.is_file():
                z.write(item, Path('DataShip') / item.relative_to(stage))


def install_nssm(archive: Path, app: Path) -> None:
    data = verified_nssm(archive)
    digest = hashlib.sha256(data).hexdigest()
    fallback = digest in (NSSM_FALLBACK_SHA256, NSSM_RC8_SHA256)
    nssm = app / 'nssm'
    (nssm / 'win64').mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as z:
        sources = [('DataShip/nssm/win64/nssm.exe', 'win64/nssm.exe'),
                   ('DataShip/nssm/README-upstream.txt', 'README-upstream.txt')] if fallback else [
                   (f'nssm-{NSSM_VERSION}/win64/nssm.exe', 'win64/nssm.exe'),
                   (f'nssm-{NSSM_VERSION}/README.txt', 'README-upstream.txt')]
        for source, target in sources:
            (nssm / target).write_bytes(z.read(source))
    provenance = f'NSSM {NSSM_VERSION} (win64)\nPublic domain\n{NSSM_URL}\nSHA256: {NSSM_SHA256}\n'
    if fallback:
        source = (f'https://api.github.com/{NSSM_FALLBACK_ASSET}' if digest == NSSM_FALLBACK_SHA256
                  else 'https://github.com/H0nz4k/MailPilot/releases/tag/dataship-v1.0.0-rc.8')
        provenance += f'Fallback: {source}\nBundle SHA256: {digest}\n'
    (nssm / 'SOURCE.txt').write_text(provenance, encoding='utf-8')


def package(app: Path, output: Path, nssm_archive: Path, commit: str) -> list[Path]:
    if (ROOT / 'VERSION').read_text().strip() != WEB_VERSION:
        raise ValueError('VERSION and services/web_branding.py disagree.')
    for name in REQUIRED_FILES:
        if not (app / name).is_file():
            raise FileNotFoundError(app / name)
    if not (app / '_internal').is_dir():
        raise FileNotFoundError('The complete onedir build including _internal is required.')
    verified_nssm(nssm_archive)
    output.mkdir(parents=True, exist_ok=True)
    prefix = f'DataShip-{WEB_VERSION}-Windows-x64'
    paths = [output / f'{prefix}.zip', output / f'{prefix}-NSSM.zip']
    # Do not silently replace an already prepared version.
    if any(p.exists() for p in [*paths, output / 'SHA256SUMS.txt']):
        raise FileExistsError('Release output already exists. Use a new empty output directory.')
    with tempfile.TemporaryDirectory(prefix='dataship-release-') as tmp:
        stage = Path(tmp) / 'DataShip'
        stage.mkdir()
        for name in REQUIRED_FILES:
            shutil.copy2(app / name, stage / name)
        shutil.copytree(app / '_internal', stage / '_internal')
        # Explicit sample, not app/config.json or .env / tasks / machine secrets.
        sample = ROOT / 'config.example.json'
        shutil.copy2(sample, stage / 'config.example.json')
        shutil.copy2(sample, stage / 'config.json')
        shutil.copy2(ROOT / 'docs/RELEASE_TEST_CHECKLIST.md', stage / 'KONTROLA_FUNKCI.md')
        shutil.copy2(ROOT / 'docs/RELEASE_WINDOWS.md', stage / 'CTETE_ME.md')
        shutil.copy2(ROOT / 'docs/CLI_EXPORT_PREHLEDU.md', stage / 'EXPORT_PREHLEDU.md')
        shutil.copy2(ROOT / 'docs/releases' / f'{WEB_VERSION}.md', stage / 'NOVINKY.md')
        metadata = {'product': 'DataShip', 'version': WEB_VERSION, 'build': WEB_BUILD, 'commit': commit,
                    'platform': 'windows-x64', 'python': sys.version.split()[0]}
        (stage / 'BUILD_INFO.json').write_text(json.dumps(metadata, indent=2)+'\n', encoding='utf-8')
        make_zip(stage, paths[0])
        install_nssm(nssm_archive, stage)
        shutil.copy2(ROOT / 'scripts/install_dataship_service.sh', stage / 'INSTALOVAT_SLUZBU.sh')
        make_zip(stage, paths[1])
    checksums = output / 'SHA256SUMS.txt'
    checksums.write_text(''.join(f'{hashlib.file_digest(p.open("rb"), "sha256").hexdigest()}  {p.name}\n' for p in paths), encoding='ascii')
    return [*paths, checksums]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, default=ROOT / 'dist-web/DataShip')
    parser.add_argument('--output', type=Path, default=ROOT / 'release-dist' / WEB_VERSION)
    parser.add_argument('--nssm-archive', type=Path)
    parser.add_argument('--commit')
    parser.add_argument('--install-nssm', type=Path, help='Install verified NSSM beside a local EXE build only.')
    args = parser.parse_args()
    archive = args.nssm_archive or ROOT / 'build' / f'nssm-{NSSM_VERSION}.zip'
    if not archive.exists():
        # Download only from the official upstream and verify before extracting.
        download_nssm(archive)
    if args.install_nssm is not None:
        install_nssm(archive, args.install_nssm)
        print(args.install_nssm / 'nssm/win64/nssm.exe')
        return
    commit = args.commit or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    for path in package(args.app, args.output, archive, commit):
        print(path)


if __name__ == '__main__':
    main()

