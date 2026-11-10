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
    (app / '_internal/BUILD_INFO.json').write_text('must not ship')
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
            readme = z.read('DataShip/README.md').decode('utf-8')
            assert '--export-report' in readme and '--export-report-id' in readme
            assert f'Novinky verze {release.WEB_VERSION}' in readme
            assert release.WEB_BUILD in readme
            assert '{{VERSION}}' not in readme and '{{BUILD}}' not in readme
            assert not any(Path(name).name.casefold() in release.EXCLUDED_DOCUMENTS for name in z.namelist())
            assert not any(name.lower().endswith('.vbs') for name in z.namelist())
            assert json.loads(z.read('DataShip/config.json')) == json.loads((release.ROOT / 'config.example.json').read_text(encoding="utf-8"))
            assert '0123456789abcdef' in readme
            assert all(b'PRIVATE-DO-NOT-SHIP' not in z.read(name) for name in z.namelist())
    with ZipFile(paths[0]) as z:
        assert 'DataShip/nssm/win64/nssm.exe' not in z.namelist()
    with ZipFile(paths[1]) as z:
        assert 'DataShip/nssm/win64/nssm.exe' in z.namelist()
        assert 'DataShip/INSTALOVAT_SLUZBU.sh' in z.namelist()
    for line in paths[2].read_text(encoding="utf-8").splitlines():
        digest, name = line.split('  ')
        assert digest == hashlib.sha256((paths[2].parent / name).read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        release.package(app, tmp_path / 'out', archive, 'different-commit')


def test_changed_nssm_archive_is_rejected(tmp_path):
    archive = tmp_path / 'tampered.zip'
    archive.write_bytes(b'tampered download')
    with pytest.raises(ValueError, match='checksum'):
        release.verified_nssm(archive)


def test_bundled_nssm_defaults_only_for_new_install(tmp_path, monkeypatch):
    from services import web_mail_settings
    monkeypatch.setattr(web_mail_settings, "application_directory", lambda: tmp_path)
    binary = tmp_path / 'nssm/win64/nssm.exe'
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'MZ-fixture')
    path = tmp_path / 'web_mail_settings.json'
    assert load_settings(path)['nssm_path'] == str(binary.resolve())
    path.write_text(json.dumps({'nssm_path': 'C:/existing/nssm.exe'}))
    assert load_settings(path)['nssm_path'] == 'C:/existing/nssm.exe'


def test_nssm_download_retries_outage_and_caches_only_verified_bytes(tmp_path, monkeypatch):
    import io
    from urllib.error import HTTPError
    data = b'complete verified upstream archive'
    monkeypatch.setattr(release, 'NSSM_SHA256', hashlib.sha256(data).hexdigest())
    calls = []
    def request(url, timeout):
        calls.append((url, timeout))
        if len(calls) < 3:
            raise HTTPError(url, 503, 'Service Temporarily Unavailable', {}, None)
        return io.BytesIO(data)
    monkeypatch.setattr(release.urllib.request, 'urlopen', request)
    monkeypatch.setattr(release.time, 'sleep', lambda _: None)
    archive = tmp_path / 'build/nssm.zip'
    release.download_nssm(archive)
    assert archive.read_bytes() == data
    assert calls == [(release.NSSM_URL, 60)] * 3
    assert list(archive.parent.iterdir()) == [archive]


def test_invalid_nssm_download_is_not_cached_or_retried(tmp_path, monkeypatch):
    import io
    calls = []
    def request(*_args, **_kwargs):
        calls.append(1)
        return io.BytesIO(b'invalid archive')
    monkeypatch.setattr(release.urllib.request, 'urlopen', request)
    archive = tmp_path / 'build/nssm.zip'
    with pytest.raises(ValueError, match='checksum'):
        release.download_nssm(archive)
    assert calls == [1]
    assert not list(archive.parent.iterdir())


def test_upstream_outage_reuses_only_nssm_from_verified_previous_release(tmp_path, monkeypatch):
    from urllib.error import HTTPError
    previous = tmp_path / 'previous.zip'
    with ZipFile(previous, 'w') as z:
        z.writestr('DataShip/nssm/win64/nssm.exe', b'MZ-verified-nssm')
        z.writestr('DataShip/nssm/README-upstream.txt', 'public domain')
        z.writestr('DataShip/DataShip.exe', b'old-gui-must-not-be-reused')
        z.writestr('DataShip/DataShip-Worker.exe', b'old-worker-must-not-be-reused')
        z.writestr('DataShip/config.json', b'old-config-must-not-be-reused')
    data = previous.read_bytes()
    monkeypatch.setattr(release, 'NSSM_FALLBACK_SHA256', hashlib.sha256(data).hexdigest())
    requests = []
    def unavailable(url, timeout):
        requests.append(url)
        raise HTTPError(url, 503, 'unavailable', {}, None)
    downloads = []
    def github_download(args, *, stdout, stderr, check):
        assert args == ['gh', 'api', '--hostname', 'github.com', release.NSSM_FALLBACK_ASSET,
                        '--header', 'Accept: application/octet-stream']
        assert check
        downloads.append(args)
        stdout.write(data)
    monkeypatch.setattr(release.urllib.request, 'urlopen', unavailable)
    monkeypatch.setattr(release.subprocess, 'run', github_download)
    monkeypatch.setattr(release.time, 'sleep', lambda _: None)
    cache = tmp_path / 'cache/nssm.zip'
    release.download_nssm(cache)
    assert len(requests) == 3
    assert len(downloads) == 1
    assert cache.read_bytes() == data
    app = tmp_path / 'new-app'
    release.install_nssm(cache, app)
    assert (app / 'nssm/win64/nssm.exe').read_bytes() == b'MZ-verified-nssm'
    assert not (app / 'DataShip.exe').exists()
    assert not (app / 'DataShip-Worker.exe').exists()
    assert not (app / 'config.json').exists()
    assert release.NSSM_FALLBACK_SHA256 in (app / 'nssm/SOURCE.txt').read_text()
    assert list(cache.parent.iterdir()) == [cache]


def test_changed_fallback_bundle_is_not_cached(tmp_path, monkeypatch):
    def github_download(_args, *, stdout, **_kwargs):
        stdout.write(b'untrusted bundle or API error')
    monkeypatch.setattr(release.subprocess, 'run', github_download)
    cache = tmp_path / 'nssm.zip'
    with pytest.raises(ValueError, match='checksum'):
        release.download_nssm_fallback(cache)
    assert not list(tmp_path.iterdir())

