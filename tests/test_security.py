import hashlib
import io
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
import pyotp
from cryptography.fernet import Fernet
from app import MAX_FILE, QUOTA, create_app


@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING': True, 'DATA_DIR': str(tmp_path), 'RATELIMIT_ENABLED': False})


def token(client, page='/login'):
    html = client.get(page).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def post(client, path, data=None, page='/vault'):
    return client.post(path, data={'csrf_token': token(client, page), **(data or {})}, follow_redirects=True)


def account(app, name='alice'):
    client = app.test_client()
    post(client, '/register', {'username': name, 'password': 'correct horse battery!'}, '/register')
    post(client, '/login', {'username': name, 'password': 'correct horse battery!'}, '/login')
    return client


def upload(client, name='notes.txt', content=b'Private project notes'):
    return post(client, '/upload', {'file': (io.BytesIO(content), name)})


def rows(app, table='files'):
    with sqlite3.connect(Path(app.config['DATA_DIR']) / 'vault.sqlite3') as db:
        db.row_factory = sqlite3.Row
        return db.execute(f'SELECT * FROM {table}').fetchall()


def test_account_password_hash_and_login(app):
    client = account(app)
    assert b'Your file vault' in client.get('/vault').data
    user = rows(app, 'users')[0]
    assert user['password_hash'].startswith('scrypt:32768:8:3$')
    assert 'correct horse battery!' not in user['password_hash']


def test_auth_required(app):
    client = app.test_client()
    for url in ['/vault', '/activity', '/files/anything/download']:
        assert client.get(url).status_code == 302


def test_csrf_required(app):
    client = account(app)
    assert client.post('/upload', data={'file': (io.BytesIO(b'x'), 'a.txt')}).status_code == 400
    assert client.post('/logout').status_code == 400


def test_upload_encrypt_download_delete(app):
    client = account(app)
    response = upload(client)
    assert b'File validated, encrypted' in response.data
    row = rows(app)[0]
    stored = (Path(app.config['DATA_DIR']) / 'vault' / row['id']).read_bytes()
    assert b'Private project notes' not in stored
    assert row['sha256'] == hashlib.sha256(b'Private project notes').hexdigest()
    result = client.get(f"/files/{row['id']}/download")
    assert result.data == b'Private project notes'
    assert result.headers['Content-Disposition'].startswith('attachment;')
    assert result.headers['Content-Type'] == 'application/octet-stream'
    post(client, f"/files/{row['id']}/delete")
    assert not rows(app)
    assert not (Path(app.config['DATA_DIR']) / 'vault' / row['id']).exists()


@pytest.mark.parametrize('name,content', [
    ('shell.php', b'<?php echo 1;'), ('image.php.jpg', b'fake'),
    ('../escape.txt', b'text'), ('bad%00.txt', b'text'),
    ('fake.png', b'not an image'), ('empty.txt', b''),
    ('binary.txt', b'\x00\x01'), ('invalid.txt', b'\xff\xfe'),
    ('vector.svg', b'<svg/>'), ('archive.zip', b'PK'),
    ('document.pdf', b'%PDF-1.7'), ('<script>.txt', b'text'),
])
def test_rejected_uploads(app, name, content):
    client = account(app)
    upload(client, name, content)
    assert not rows(app)
    assert rows(app, 'events')[-1]['action'] == 'Upload rejected'


def test_image_normalization(app):
    client = account(app)
    raw = io.BytesIO()
    Image.new('RGB', (20, 20), 'green').save(raw, 'PNG')
    upload(client, 'picture.png', raw.getvalue() + b'TRAILING_MARKER')
    row = rows(app)[0]
    result = client.get(f"/files/{row['id']}/download")
    assert b'TRAILING_MARKER' not in result.data
    with Image.open(io.BytesIO(result.data)) as img:
        assert img.format == 'PNG'


def test_exif_metadata_removed(app):
    client = account(app)
    original = io.BytesIO()
    exif = Image.Exif()
    exif[315] = 'PRIVATE_AUTHOR_METADATA'
    Image.new('RGB', (20, 20), 'blue').save(original, 'JPEG', exif=exif)
    upload(client, 'photo.jpg', original.getvalue())
    result = client.get(f"/files/{rows(app)[0]['id']}/download")
    assert b'PRIVATE_AUTHOR_METADATA' not in result.data
    with Image.open(io.BytesIO(result.data)) as img:
        assert not img.getexif()


def test_declared_mime_mismatch(app):
    client = account(app)
    result = post(client, '/upload', {'file': (io.BytesIO(b'hello'), 'notes.txt', 'image/png')})
    assert b'declared MIME type' in result.data
    assert not rows(app)


def test_valid_magic_but_invalid_structure(app):
    client = account(app)
    upload(client, 'fake.png', b'\x89PNG\r\n\x1a\ninvalid')
    assert not rows(app)


def test_image_dimension_limit(app):
    raw = io.BytesIO()
    Image.new('1', (4001, 4000)).save(raw, 'PNG')
    upload(account(app), 'huge.png', raw.getvalue())
    assert not rows(app)


def test_mfa_enrollment_login_and_replay(app):
    client = account(app)
    password = 'correct horse battery!'
    post(client, '/security', {'action': 'start', 'password': password})
    assert client.get('/security/qr').mimetype == 'image/png'
    cipher = Fernet((Path(app.config['DATA_DIR']) / 'encryption.key').read_bytes())
    secret = cipher.decrypt(rows(app, 'users')[0]['totp_pending']).decode()
    totp = pyotp.TOTP(secret)
    post(client, '/security', {'action': 'enable', 'password': password, 'otp': totp.now()})
    assert rows(app, 'users')[0]['totp_secret']
    assert client.get('/security/qr').status_code == 404
    post(client, '/logout')
    result = post(client, '/login', {'username': 'alice', 'password': password}, '/login')
    assert b'Invalid username' in result.data
    result = post(client, '/login', {'username': 'alice', 'password': password, 'otp': totp.now()}, '/login')
    assert b'Invalid username' in result.data
    # Simulate a fresh, accepted time step without sleeping.
    with sqlite3.connect(Path(app.config['DATA_DIR']) / 'vault.sqlite3') as db:
        db.execute('UPDATE users SET totp_last=?', (int(time.time()) // 30 - 1,))
    post(client, '/login', {'username': 'alice', 'password': password, 'otp': totp.now()}, '/login')
    assert client.get('/vault').status_code == 200
    with sqlite3.connect(Path(app.config['DATA_DIR']) / 'vault.sqlite3') as db:
        db.execute('UPDATE users SET totp_last=?', (int(time.time()) // 30 - 1,))
    post(client, '/security', {'action': 'disable', 'password': password, 'otp': totp.now()})
    assert rows(app, 'users')[0]['totp_secret'] is None


def test_cross_account_access_and_audit_isolation(app):
    alice = account(app)
    upload(alice, 'private_alice.txt')
    row = rows(app)[0]
    bob = account(app, 'bob')
    assert b'private_alice.txt' not in bob.get('/vault').data
    assert b'private_alice.txt' not in bob.get('/activity').data
    assert bob.get(f"/files/{row['id']}/download").status_code == 404
    assert post(bob, f"/files/{row['id']}/delete").status_code == 404
    assert len(rows(app)) == 1


def test_tampered_ciphertext_fails_closed(app):
    client = account(app)
    upload(client)
    row = rows(app)[0]
    (Path(app.config['DATA_DIR']) / 'vault' / row['id']).write_bytes(b'corrupted')
    assert client.get(f"/files/{row['id']}/download").status_code == 409
    assert rows(app, 'events')[-1]['action'] == 'Integrity check failed'


def test_limit_and_quota(app):
    client = account(app)
    upload(client, 'big.txt', b'x' * (MAX_FILE + 1))
    assert not rows(app)
    upload(client)
    with sqlite3.connect(Path(app.config['DATA_DIR']) / 'vault.sqlite3') as db:
        db.execute('UPDATE files SET size=?', (QUOTA,))
    assert b'quota would be exceeded' in upload(client, 'second.txt').data
    assert len(rows(app)) == 1


def test_http_request_limit(app):
    client = account(app)
    assert upload(client, 'too_big.txt', b'x' * (MAX_FILE + 200_000)).status_code == 413


def test_security_headers(app):
    result = app.test_client().get('/login')
    assert result.headers['X-Content-Type-Options'] == 'nosniff'
    assert "frame-ancestors 'none'" in result.headers['Content-Security-Policy']
    assert 'HttpOnly' in result.headers['Set-Cookie']
    assert 'SameSite=Lax' in result.headers['Set-Cookie']


def test_logout_revokes_copied_cookie(app):
    client = account(app)
    old_cookie = client.get_cookie('session').value
    post(client, '/logout')
    client.set_cookie('session', old_cookie)
    assert client.get('/vault').status_code == 302


def test_expired_session(app):
    client = account(app)
    with sqlite3.connect(Path(app.config['DATA_DIR']) / 'vault.sqlite3') as db:
        db.execute('UPDATE sessions SET expires_at=0')
    assert client.get('/vault').status_code == 302


def test_revoke_all_devices(app):
    first = account(app)
    second = app.test_client()
    post(second, '/login', {'username': 'alice', 'password': 'correct horse battery!'}, '/login')
    assert second.get('/vault').status_code == 200
    post(first, '/security/revoke-sessions', {'password': 'correct horse battery!'})
    assert second.get('/vault').status_code == 302
    assert first.get('/vault').status_code == 302


def test_audit_tampering_detected(app):
    client = account(app)
    upload(client)
    assert b'Audit chain verified' in client.get('/activity').data
    with sqlite3.connect(Path(app.config['DATA_DIR']) / 'vault.sqlite3') as db:
        db.execute("UPDATE events SET detail='altered' WHERE action='File uploaded'")
    assert b'Audit integrity warning' in client.get('/activity').data


def test_required_scanner_missing(app):
    app.config['REQUIRE_SCAN'] = True
    client = account(app)
    assert b'paused' in upload(client).data
    assert not rows(app)


@pytest.mark.parametrize('result,expected', [(0, True), (1, False), (2, False)])
def test_scanner_contract(app, monkeypatch, result, expected):
    app.config['SCANNER'] = 'configured-clamscan'
    def fake_scan(args, **kwargs):
        assert args[:2] == ['configured-clamscan', '--no-summary']
        assert Path(args[2]).read_bytes() == b'Private project notes'
        assert kwargs['timeout'] == 30
        return SimpleNamespace(returncode=result)
    monkeypatch.setattr(subprocess, 'run', fake_scan)
    upload(account(app))
    assert bool(rows(app)) is expected
    assert not list(Path(app.config['DATA_DIR']).glob('*.scan'))


def test_scanner_timeout(app, monkeypatch):
    app.config['SCANNER'] = 'configured-clamscan'
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('scanner', 30)
    monkeypatch.setattr(subprocess, 'run', timeout)
    upload(account(app))
    assert not rows(app)
    assert not list(Path(app.config['DATA_DIR']).glob('*.scan'))


def test_login_rate_limit(tmp_path):
    application = create_app({'TESTING': True, 'DATA_DIR': str(tmp_path)})
    client = application.test_client()
    for _ in range(10):
        response = post(client, '/login', {'username': 'missing', 'password': 'incorrect'}, '/login')
        assert response.status_code == 200
    assert post(client, '/login', {'username': 'missing', 'password': 'incorrect'}, '/login').status_code == 429


def test_restart_preserves_encryption_and_files(app):
    client = account(app)
    upload(client)
    row = rows(app)[0]
    restarted = create_app({'TESTING': True, 'DATA_DIR': app.config['DATA_DIR'], 'RATELIMIT_ENABLED': False})
    other = restarted.test_client()
    post(other, '/login', {'username': 'alice', 'password': 'correct horse battery!'}, '/login')
    assert other.get(f"/files/{row['id']}/download").data == b'Private project notes'

