"""Release bundles exclude local configuration and pin the upstream NSSM bytes."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from scripts import package_web_release as release
from services.web_mail_settings import load_settings


def test_release_packages_only_program_and_clean_sample(tmp_path, monkeypatch):
    app = tmp_path / 'app'
    app.mkdir()
    for name in release.REQUIRED_FILES:
        (app / name).write_bytes(b'MZ-test-fixture')
    (app / '_internal').mkdir()
    (app / '_internal/runtime.dll').write_bytes(b'test-runtime')
    for name in ['config.json', '.env', 'web_mail_tasks.json', 'daily_reports.json', 'web_mail_settings.json']:
        (app / name).write_text('PRIVATE-DO-NOT-SHIP')
    archive = tmp_path / 'nssm.zip'
    with ZipFile(archive, 'w') as z:
        z.writestr(f'nssm-{release.NSSM_VERSION}/win64/nssm.exe', b'MZ-nssm-fixture')
        z.writestr(f'nssm-{release.NSSM_VERSION}/README.txt', 'public domain fixture')
    monkeypatch.setattr(release, 'NSSM_SHA256', hashlib.sha256(archive.read_bytes()).hexdigest())
    paths = release.package(app, tmp_path / 'out', archive, '0123456789abcdef')
    for path in paths[:2]:
        with ZipFile(path) as z:
            assert 'DataShip/_internal/runtime.dll' in z.namelist()
            assert json.loads(z.read('DataShip/config.json')) == json.loads((release.ROOT / 'config.example.json').read_text())
            assert json.loads(z.read('DataShip/BUILD_INFO.json'))['commit'] == '0123456789abcdef'
            assert all(b'PRIVATE-DO-NOT-SHIP' not in z.read(name) for name in z.namelist())
    with ZipFile(paths[0]) as z:
        assert 'DataShip/nssm/nssm.exe' not in z.namelist()
    with ZipFile(paths[1]) as z:
        assert 'DataShip/nssm/nssm.exe' in z.namelist()
        assert 'DataShip/INSTALOVAT_SLUZBU.sh' in z.namelist()
    for line in paths[2].read_text().splitlines():
        digest, name = line.split('  ')
        assert digest == hashlib.sha256((paths[2].parent / name).read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        release.package(app, tmp_path / 'out', archive, 'different-commit')


def test_changed_nssm_archive_is_rejected(tmp_path):
    archive = tmp_path / 'tampered.zip'
    archive.write_bytes(b'tampered download')
    with pytest.raises(ValueError, match='checksum'):
        release.verified_nssm(archive)


def test_bundled_nssm_defaults_only_for_new_install(tmp_path):
    binary = tmp_path / 'nssm/nssm.exe'
    binary.parent.mkdir()
    binary.write_bytes(b'MZ-fixture')
    path = tmp_path / 'web_mail_settings.json'
    assert load_settings(path)['nssm_path'] == str(binary.resolve())
    path.write_text(json.dumps({'nssm_path': 'C:/existing/nssm.exe'}))
    assert load_settings(path)['nssm_path'] == 'C:/existing/nssm.exe'
