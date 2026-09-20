"""Secure File Upload System: an educational, private file vault."""
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import subprocess
import tempfile
import time
import warnings
from datetime import timedelta
from functools import wraps
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from PIL import Image, UnidentifiedImageError
import pyotp
import qrcode
from werkzeug.security import check_password_hash, generate_password_hash

MAX_FILE = 5 * 1024 * 1024
QUOTA = 50 * 1024 * 1024


def _find_clamscan():
    """Auto-detect ClamAV on common installation paths when CLAMSCAN_PATH is not set."""
    explicit = os.getenv('CLAMSCAN_PATH', '')
    if explicit:
        return explicit
    app_dir = Path(__file__).resolve().parent.parent
    portable_dirs = sorted(app_dir.glob('.clamav/clamav-*'), reverse=True)
    candidates = [str(d / 'clamscan.exe') for d in portable_dirs]
    candidates += [
        os.path.join(os.environ.get('ProgramFiles', ''), 'ClamAV', 'clamscan.exe'),
        os.path.join(os.environ.get('ProgramFiles(x86)', ''), 'ClamAV', 'clamscan.exe'),
        '/usr/bin/clamscan',
        '/usr/local/bin/clamscan',
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ''


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    detected_scanner = _find_clamscan()
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=MAX_FILE + 128 * 1024,
        MAX_FORM_MEMORY_SIZE=64 * 1024,
        MAX_FORM_PARTS=10,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.getenv('APP_HTTPS') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        SCANNER=detected_scanner,
        REQUIRE_SCAN=os.getenv('REQUIRE_SCAN') == '1',
        DATA_DIR=os.getenv('DATA_DIR', app.instance_path),
        RATELIMIT_STORAGE_URI=os.getenv('RATELIMIT_STORAGE_URI', 'memory://'),
    )
    if detected_scanner and not os.getenv('CLAMSCAN_PATH'):
        print(f'[SecureVault] Auto-detected ClamAV at: {detected_scanner}')
    if test_config:
        app.config.update(test_config)
    root = Path(app.config['DATA_DIR']).resolve()
    root.mkdir(parents=True, exist_ok=True)
    vault = root / 'vault'
    vault.mkdir(exist_ok=True)

    def persistent_secret(name, factory):
        path = root / name
        if not path.exists():
            try:
                with path.open('xb') as stream:
                    stream.write(factory())
                path.chmod(0o600)
            except FileExistsError:
                pass
        return path.read_bytes()

    app.config['SECRET_KEY'] = persistent_secret('session.key', lambda: secrets.token_bytes(32))
    cipher = Fernet(persistent_secret('encryption.key', Fernet.generate_key))
    audit_key = persistent_secret('audit.key', lambda: secrets.token_bytes(32))
    CSRFProtect(app)
    limiter = Limiter(get_remote_address, app=app, default_limits=['300 per minute'])
    app.extensions['vault_limiter'] = limiter

    def db():
        if 'db' not in g:
            g.db = sqlite3.connect(root / 'vault.sqlite3', timeout=15)
            g.db.row_factory = sqlite3.Row
            g.db.execute('PRAGMA foreign_keys=ON')
        return g.db

    @app.teardown_appcontext
    def close_db(_error):
        connection = g.pop('db', None)
        if connection is not None:
            connection.close()

    with app.app_context():
        db().executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS files (
          id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id),
          name TEXT NOT NULL, size INTEGER NOT NULL, mime TEXT NOT NULL,
          sha256 TEXT NOT NULL, scan TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id),
          action TEXT NOT NULL, detail TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
          expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS shares (
          token_hash TEXT PRIMARY KEY, file_id TEXT NOT NULL REFERENCES files(id) ON DELETE CASCADE,
          owner_id INTEGER NOT NULL REFERENCES users(id), expires_at INTEGER NOT NULL,
          used_at INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE INDEX IF NOT EXISTS files_owner ON files(owner_id);
        CREATE INDEX IF NOT EXISTS events_user ON events(user_id, id);
        ''')
        columns = {row['name'] for row in db().execute('PRAGMA table_info(users)')}
        for name, kind in [('totp_secret', 'BLOB'), ('totp_pending', 'BLOB'), ('totp_last', 'INTEGER DEFAULT -1')]:
            if name not in columns:
                db().execute(f'ALTER TABLE users ADD COLUMN {name} {kind}')
        event_columns = {row['name'] for row in db().execute('PRAGMA table_info(events)')}
        file_columns = {row['name'] for row in db().execute('PRAGMA table_info(files)')}
        if 'processing' not in file_columns:
            db().execute("ALTER TABLE files ADD COLUMN processing TEXT NOT NULL DEFAULT 'Not recorded for older upload'")
        if 'chain_mac' not in event_columns:
            db().execute('ALTER TABLE events ADD COLUMN chain_mac TEXT')
        db().commit()

    def audit_mac(previous, row):
        encoded = json.dumps([previous, row['id'], row['user_id'], row['action'], row['detail'],
                              row['created_at']], ensure_ascii=True, separators=(',', ':')).encode()
        return hmac.new(audit_key, encoded, hashlib.sha256).hexdigest()

    def event(action, detail='', user_id=None):
        connection = db()
        owner = user_id if user_id is not None else session.get('uid')
        connection.execute('BEGIN IMMEDIATE')
        try:
            previous = connection.execute('SELECT chain_mac FROM events WHERE user_id IS ? ORDER BY id DESC LIMIT 1',
                                          (owner,)).fetchone()
            cursor = connection.execute('INSERT INTO events(user_id, action, detail) VALUES(?,?,?)',
                                        (owner, action, detail[:200]))
            row = connection.execute('SELECT * FROM events WHERE id=?', (cursor.lastrowid,)).fetchone()
            digest = audit_mac((previous['chain_mac'] or '') if previous else '', row)
            connection.execute('UPDATE events SET chain_mac=? WHERE id=?', (digest, cursor.lastrowid))
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def login_required(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.user is None:
                return redirect(url_for('login'))
            return fn(*args, **kwargs)
        return wrapper

    @app.before_request
    def current_user():
        token_hash = hashlib.sha256(session.get('sid', '').encode()).hexdigest()
        g.user = db().execute('SELECT users.id, username FROM users JOIN sessions ON users.id=sessions.user_id '
                             'WHERE token_hash=? AND expires_at>?', (token_hash, int(time.time()))).fetchone()
        if g.user is None:
            session.pop('uid', None)

    @app.after_request
    def headers(response):
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if app.config['SESSION_COOKIE_SECURE']:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @app.route('/register', methods=['GET', 'POST'])
    @limiter.limit('5 per minute', methods=['POST'])
    def register():
        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()
            password = request.form.get('password', '')
            if not re.fullmatch(r'[a-z0-9_]{3,32}', username):
                flash('Use 3–32 letters, numbers or underscores for your username.', 'error')
            elif not 12 <= len(password) <= 128:
                flash('Use a password between 12 and 128 characters.', 'error')
            else:
                try:
                    cursor = db().execute('INSERT INTO users(username,password_hash) VALUES(?,?)',
                                          (username, generate_password_hash(password, method='scrypt:32768:8:3')))
                    db().commit()
                    event('Account created', user_id=cursor.lastrowid)
                    flash('Account created. Sign in to your vault.', 'success')
                    return redirect(url_for('login'))
                except sqlite3.IntegrityError:
                    db().rollback()
                    flash('That username is unavailable.', 'error')
        return render_template('auth.html', registering=True)

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit('10 per minute', methods=['POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()
            password = request.form.get('password', '')
            user = db().execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
            # Bound expensive password work; use a dummy hash to reduce username timing leaks.
            valid = len(password) <= 128 and check_password_hash(
                user['password_hash'] if user else app.config['DUMMY_HASH'], password)
            if user and valid and user['totp_secret']:
                valid = consume_otp(user, request.form.get('otp', ''))
            if user and valid:
                previous = session.get('sid', '')
                db().execute('DELETE FROM sessions WHERE token_hash=? OR expires_at<=?',
                             (hashlib.sha256(previous.encode()).hexdigest(), int(time.time())))
                session.clear()
                token = secrets.token_urlsafe(32)
                db().execute('INSERT INTO sessions VALUES(?,?,?)',
                             (hashlib.sha256(token.encode()).hexdigest(), user['id'], int(time.time()) + 1800))
                db().commit()
                session['sid'] = token
                session['uid'] = user['id']
                session.permanent = True
                event('Signed in')
                return redirect(url_for('dashboard'))
            event('Failed sign in', user_id=user['id'] if user else None)
            flash('Invalid username, password or authenticator code.', 'error')
        return render_template('auth.html', registering=False)

    app.config['DUMMY_HASH'] = generate_password_hash(secrets.token_urlsafe(24), method='scrypt:32768:8:3')

    def consume_otp(user, code):
        if not re.fullmatch(r'\d{6}', code):
            return False
        secret = cipher.decrypt(user['totp_secret']).decode()
        totp = pyotp.TOTP(secret)
        step = int(time.time()) // 30
        for candidate in (step, step - 1, step + 1):
            if totp.verify(code, for_time=candidate * 30):
                cursor = db().execute('UPDATE users SET totp_last=? WHERE id=? AND totp_last<?',
                                      (candidate, user['id'], candidate))
                db().commit()
                return cursor.rowcount == 1
        return False

    @app.route('/security', methods=['GET', 'POST'])
    @login_required
    @limiter.limit('10 per minute', methods=['POST'])
    def security():
        user = db().execute('SELECT * FROM users WHERE id=?', (g.user['id'],)).fetchone()
        if request.method == 'POST':
            password = request.form.get('password', '')
            if len(password) > 128 or not check_password_hash(user['password_hash'], password):
                flash('Enter your current password to change two-factor authentication.', 'error')
            elif request.form.get('action') == 'start' and not user['totp_secret']:
                db().execute('UPDATE users SET totp_pending=? WHERE id=?',
                             (cipher.encrypt(pyotp.random_base32().encode()), user['id']))
                db().commit()
                flash('Scan the QR code, then confirm with a code from your authenticator app.', 'success')
            elif request.form.get('action') == 'enable' and user['totp_pending'] and not user['totp_secret']:
                secret = cipher.decrypt(user['totp_pending']).decode()
                code = request.form.get('otp', '')
                if re.fullmatch(r'\d{6}', code) and pyotp.TOTP(secret).verify(code):
                    db().execute('UPDATE users SET totp_secret=totp_pending, totp_pending=NULL, totp_last=? WHERE id=?',
                                 (int(time.time()) // 30, user['id']))
                    db().execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',
                                 (user['id'], hashlib.sha256(session['sid'].encode()).hexdigest()))
                    db().commit()
                    event('Two-factor authentication enabled')
                    flash('Two-factor authentication enabled. Keep your authenticator backup safe.', 'success')
                else:
                    flash('Invalid code. Check your phone time and try again.', 'error')
            elif request.form.get('action') == 'disable' and user['totp_secret']:
                if consume_otp(user, request.form.get('otp', '')):
                    db().execute('UPDATE users SET totp_secret=NULL,totp_pending=NULL,totp_last=-1 WHERE id=?', (user['id'],))
                    db().commit()
                    event('Two-factor authentication disabled')
                    flash('Two-factor authentication disabled.', 'success')
                else:
                    flash('Enter a fresh authenticator code.', 'error')
            return redirect(url_for('security'))
        pending = cipher.decrypt(user['totp_pending']).decode() if user['totp_pending'] else None
        return render_template('security.html', enabled=bool(user['totp_secret']), pending=pending)

    @app.get('/security/qr')
    @login_required
    def security_qr():
        user = db().execute('SELECT * FROM users WHERE id=?', (g.user['id'],)).fetchone()
        if not user['totp_pending'] or user['totp_secret']:
            abort(404)
        secret = cipher.decrypt(user['totp_pending']).decode()
        uri = pyotp.TOTP(secret).provisioning_uri(name=user['username'], issuer_name='SecureVault')
        output = io.BytesIO()
        qrcode.make(uri).save(output, format='PNG')
        output.seek(0)
        return send_file(output, mimetype='image/png')

    @app.post('/security/revoke-sessions')
    @login_required
    @limiter.limit('5 per minute')
    def revoke_sessions():
        user = db().execute('SELECT * FROM users WHERE id=?', (g.user['id'],)).fetchone()
        password = request.form.get('password', '')
        valid = len(password) <= 128 and check_password_hash(user['password_hash'], password)
        if valid and user['totp_secret']:
            valid = consume_otp(user, request.form.get('otp', ''))
        if not valid:
            flash('Enter your current password and, if enabled, a fresh authenticator code.', 'error')
            return redirect(url_for('security'))
        event('All sessions revoked')
        db().execute('DELETE FROM sessions WHERE user_id=?', (g.user['id'],))
        db().commit()
        session.clear()
        flash('All devices have been signed out.', 'success')
        return redirect(url_for('login'))

    @app.post('/logout')
    @login_required
    def logout():
        event('Signed out')
        db().execute('DELETE FROM sessions WHERE token_hash=?',
                     (hashlib.sha256(session.get('sid', '').encode()).hexdigest(),))
        db().commit()
        session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    def landing():
        return render_template('landing.html')

    @app.get('/vault')
    @login_required
    def dashboard():
        files = db().execute('SELECT * FROM files WHERE owner_id=? ORDER BY created_at DESC, id',
                             (g.user['id'],)).fetchall()
        used = sum(row['size'] for row in files)
        return render_template('dashboard.html', files=files, used=used, quota=QUOTA,
                               scanner=bool(app.config['SCANNER']), required=app.config['REQUIRE_SCAN'])

    def validate(upload):
        name = upload.filename or ''
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,95}\.(txt|png|jpg|jpeg)', name, re.I):
            raise ValueError('Use a simple filename with one extension: TXT, PNG, JPG or JPEG.')
        raw = upload.read(MAX_FILE + 1)
        if not raw or len(raw) > MAX_FILE:
            raise ValueError('Files must be nonempty and no larger than 5 MiB.')
        ext = name.rsplit('.', 1)[1].lower()
        expected_mime = {'txt': 'text/plain', 'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg'}[ext]
        if upload.mimetype not in (expected_mime, 'application/octet-stream', ''):
            raise ValueError('The declared MIME type does not match the filename extension.')
        if ext == 'txt':
            try:
                content = raw.decode('utf-8')
            except UnicodeDecodeError:
                raise ValueError('TXT files must contain valid UTF-8 text.') from None
            if any(ord(char) < 32 and char not in '\t\n\r' for char in content):
                raise ValueError('Binary control characters are not allowed in TXT files.')
            mime = 'text/plain'
        else:
            expected = 'PNG' if ext == 'png' else 'JPEG'
            magic = b'\x89PNG\r\n\x1a\n' if expected == 'PNG' else b'\xff\xd8\xff'
            if not raw.startswith(magic):
                raise ValueError('The file magic bytes do not match the image extension.')
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(raw)) as picture:
                        if picture.format != expected or picture.width * picture.height > 16_000_000:
                            raise ValueError('Image type mismatch or image exceeds 16 megapixels.')
                        picture.verify()
                    with Image.open(io.BytesIO(raw)) as picture:
                        picture.load()
                        clean = io.BytesIO()
                        converted = picture.convert('RGB' if expected == 'JPEG' else 'RGBA')
                        converted.info.clear()
                        converted.save(clean, format=expected)
                        raw = clean.getvalue()
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                raise ValueError('The image is malformed or unsafe to process.') from None
            if len(raw) > MAX_FILE:
                raise ValueError('The normalized image exceeds 5 MiB.')
            mime = 'image/png' if expected == 'PNG' else 'image/jpeg'
        return name, raw, mime

    def _scanner_db_args():
        """Build database arguments for portable ClamAV installs."""
        scanner = app.config['SCANNER']
        if not scanner:
            return []
        db_dir = Path(scanner).parent / 'database'
        if db_dir.is_dir() and any(db_dir.glob('*.c?d')):
            return [f'--database={db_dir}']
        return []

    def scan(raw):
        scanner = app.config['SCANNER']
        if not scanner:
            if app.config['REQUIRE_SCAN']:
                raise ValueError('Uploads are paused until the antivirus scanner is configured.')
            return 'Not scanned'
        path = None
        try:
            with tempfile.NamedTemporaryFile(dir=root, suffix='.scan', delete=False) as stream:
                path = Path(stream.name)
                stream.write(raw)
            cmd = [scanner, '--no-summary'] + _scanner_db_args() + [str(path)]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 1:
                # Extract the threat name from ClamAV output
                stdout = result.stdout.decode('utf-8', errors='replace').strip()
                threat = 'unknown threat'
                if 'FOUND' in stdout:
                    # ClamAV output format: /path/to/file: ThreatName FOUND
                    parts = stdout.split(':')
                    if len(parts) >= 2:
                        threat = parts[-1].replace('FOUND', '').strip()
                raise ValueError(f'Antivirus detected a threat: {threat}. File rejected.')
            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace').strip()
                app.logger.warning('ClamAV error (exit %d): %s', result.returncode, stderr[:200])
                raise ValueError('Antivirus scanner error. Upload rejected for safety.')
            return 'ClamAV: clean'
        except (OSError, subprocess.TimeoutExpired) as exc:
            app.logger.warning('ClamAV unavailable: %s', exc)
            raise ValueError('Antivirus scanner is unavailable. Upload rejected for safety.') from None
        finally:
            if path:
                path.unlink(missing_ok=True)

    def _check_scanner_health():
        """Check if ClamAV is reachable and has valid virus databases."""
        scanner = app.config['SCANNER']
        if not scanner:
            return {'available': False, 'reason': 'No scanner configured'}
        try:
            result = subprocess.run([scanner, '--version'], capture_output=True, timeout=10)
            if result.returncode == 0:
                version = result.stdout.decode('utf-8', errors='replace').strip()
                return {'available': True, 'engine': version}
            return {'available': False, 'reason': f'Exit code {result.returncode}'}
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {'available': False, 'reason': str(exc)}

    @app.post('/upload')
    @login_required
    @limiter.limit('20 per minute')
    def upload():
        file = request.files.get('file')
        try:
            if not file:
                raise ValueError('Choose a file to upload.')
            name, raw, mime = validate(file)
            document_result = None
            if request.form.get('document_scan') == '1':
                from .document_scanner import scan_document
                raw, document_result = scan_document(raw, mime)
            scan_result = scan(raw)
            identity = secrets.token_hex(16)
            encrypted = cipher.encrypt(raw)
            connection = db()
            # Serialize quota check and insert so simultaneous uploads cannot exceed quota.
            connection.execute('BEGIN IMMEDIATE')
            used, count = connection.execute('SELECT COALESCE(SUM(size),0), COUNT(*) FROM files WHERE owner_id=?',
                                              (g.user['id'],)).fetchone()
            if used + len(raw) > QUOTA:
                connection.rollback()
                raise ValueError('Your 50 MiB storage quota would be exceeded.')
            if count >= 200:
                connection.rollback()
                raise ValueError('Your vault has reached its 200-file limit. Delete a file first.')
            target = vault / identity
            try:
                with target.open('xb') as stream:
                    stream.write(encrypted)
                connection.execute('INSERT INTO files(id,owner_id,name,size,mime,sha256,scan,processing) VALUES(?,?,?,?,?,?,?,?)',
                                   (identity, g.user['id'], name, len(raw), mime,
                                    hashlib.sha256(raw).hexdigest(), scan_result, document_result or 'Not requested'))
                connection.commit()
            except Exception:
                connection.rollback()
                target.unlink(missing_ok=True)
                raise
            event('File uploaded', name)
            if document_result:
                event('Document processed', document_result)
                flash(document_result, 'success')
            flash('File validated, encrypted and saved to your vault.', 'success')
        except ValueError as error:
            event('Upload rejected', str(error))
            flash(str(error), 'error')
        return redirect(url_for('dashboard'))

    def owned(identity):
        row = db().execute('SELECT * FROM files WHERE id=? AND owner_id=?',
                           (identity, g.user['id'])).fetchone()
        if row is None:
            abort(404)
        return row

    @app.get('/files/<identity>/download')
    @login_required
    def download(identity):
        row = owned(identity)
        raw = verified_bytes(row)
        event('File downloaded', row['name'])
        return send_file(io.BytesIO(raw), mimetype='application/octet-stream',
                         as_attachment=True, download_name=row['name'])

    def verified_bytes(row):
        try:
            raw = cipher.decrypt((vault / row['id']).read_bytes())
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise InvalidToken
        except (InvalidToken, OSError):
            event('Integrity check failed', row['name'], user_id=row['owner_id'])
            abort(409, description='This file could not be verified. Contact the operator.')
        return raw

    @app.get('/files/<identity>/inspection')
    @login_required
    def inspection(identity):
        row = owned(identity)
        verified_bytes(row)
        report = {
            'file_name': row['name'], 'mime': row['mime'], 'normalized_size_bytes': row['size'],
            'sha256': row['sha256'], 'uploaded_at_utc': row['created_at'],
            'validation': 'Passed filename, MIME, decoded content and resource checks at upload',
            'normalization': 'Image reconstructed without original metadata' if row['mime'] != 'text/plain' else 'UTF-8 and control-character checks',
            'document_processing': row['processing'], 'antivirus': row['scan'],
            'integrity': 'Fernet authentication and plaintext SHA-256 verified at report generation',
            'storage': 'Server-side Fernet encryption; owner authorization enforced',
            'limitation': 'This report is not a malware-free certificate or independent attestation.'}
        return send_file(io.BytesIO(json.dumps(report, indent=2).encode()), mimetype='application/json',
                         as_attachment=True, download_name=row['name'] + '.inspection.json')

    @app.get('/files/<identity>/preview')
    @login_required
    def preview(identity):
        row = owned(identity)
        raw = verified_bytes(row)
        if row['mime'] not in ('image/png', 'image/jpeg'):
            abort(404)
        return send_file(io.BytesIO(raw), mimetype=row['mime'], as_attachment=False)

    @app.post('/files/<identity>/share')
    @login_required
    @limiter.limit('10 per minute')
    def create_share(identity):
        row = owned(identity)
        # Verify availability before issuing a capability; it will be checked again on redemption.
        verified_bytes(row)
        code = secrets.token_hex(12).upper()
        digest = hashlib.sha256(code.encode()).hexdigest()
        expiry = int(time.time()) + 15 * 60
        db().execute('BEGIN IMMEDIATE')
        count = db().execute('SELECT COUNT(*) FROM shares WHERE owner_id=? AND expires_at>? AND used_at IS NULL',
                             (g.user['id'], int(time.time()))).fetchone()[0]
        if count >= 20:
            db().rollback()
            flash('You already have 20 active codes. Revoke a code or wait for it to expire.', 'error')
            return redirect(url_for('shares'))
        db().execute('INSERT INTO shares(token_hash,file_id,owner_id,expires_at) VALUES(?,?,?,?)',
                     (digest, row['id'], g.user['id'], expiry))
        db().commit()
        event('Share code created', row['name'])
        formatted = '-'.join(code[index:index+4] for index in range(0,24,4))
        return render_template('share_created.html', code=formatted, file=row)

    @app.get('/shares')
    @login_required
    def shares():
        rows = db().execute('SELECT shares.*,files.name FROM shares JOIN files ON files.id=shares.file_id '
                            'WHERE shares.owner_id=? ORDER BY shares.created_at DESC LIMIT 100',
                            (g.user['id'],)).fetchall()
        return render_template('shares.html', shares=rows, now=int(time.time()))

    @app.post('/shares/<digest>/revoke')
    @login_required
    def revoke_share(digest):
        cursor = db().execute('DELETE FROM shares WHERE token_hash=? AND owner_id=?', (digest, g.user['id']))
        db().commit()
        if not cursor.rowcount:
            abort(404)
        event('Share code revoked')
        flash('Share code revoked.', 'success')
        return redirect(url_for('shares'))

    @app.route('/receive', methods=['GET', 'POST'])
    @limiter.limit('10 per minute', methods=['POST'])
    def receive():
        if request.method == 'POST':
            code = request.form.get('code', '').replace('-', '').replace(' ', '').upper()
            if not re.fullmatch('[A-F0-9]{24}', code):
                flash('Enter a valid 24-character share code.', 'error')
                return render_template('receive.html'), 400
            digest = hashlib.sha256(code.encode()).hexdigest()
            row = db().execute('SELECT files.*,shares.expires_at,shares.used_at FROM shares '
                               'JOIN files ON files.id=shares.file_id WHERE token_hash=?', (digest,)).fetchone()
            if row is None or row['used_at'] is not None or row['expires_at'] <= int(time.time()):
                flash('This code is invalid, expired, revoked or already used.', 'error')
                return render_template('receive.html'), 404
            raw = verified_bytes(row)
            # Compare-and-update makes the capability single-use under concurrent requests.
            cursor = db().execute('UPDATE shares SET used_at=? WHERE token_hash=? AND used_at IS NULL AND expires_at>?',
                                  (int(time.time()), digest, int(time.time())))
            db().commit()
            if cursor.rowcount != 1:
                flash('This code has expired or was already used.', 'error')
                return render_template('receive.html'), 404
            event('Shared file downloaded', row['name'], user_id=row['owner_id'])
            return send_file(io.BytesIO(raw), mimetype='application/octet-stream',
                             as_attachment=True, download_name=row['name'])
        return render_template('receive.html')

    @app.post('/files/<identity>/delete')
    @login_required
    def delete(identity):
        row = owned(identity)
        (vault / row['id']).unlink(missing_ok=True)
        db().execute('DELETE FROM files WHERE id=? AND owner_id=?', (identity, g.user['id']))
        db().commit()
        event('File deleted', row['name'])
        flash('File deleted.', 'success')
        return redirect(url_for('dashboard'))

    @app.get('/activity')
    @login_required
    def activity():
        history = db().execute('SELECT * FROM events WHERE user_id=? ORDER BY id', (g.user['id'],)).fetchall()
        previous, verified = '', True
        for row in history:
            if not row['chain_mac'] or not hmac.compare_digest(row['chain_mac'], audit_mac(previous, row)):
                verified = False
                break
            previous = row['chain_mac']
        rows = db().execute('SELECT * FROM events WHERE user_id=? ORDER BY id DESC LIMIT 100',
                            (g.user['id'],)).fetchall()
        return render_template('activity.html', events=rows, verified=verified)

    @app.get('/health')
    @limiter.exempt
    def health():
        db().execute('SELECT 1').fetchone()
        scanner_info = _check_scanner_health()
        return {
            'status': 'ok',
            'antivirus': scanner_info,
            'require_scan': app.config['REQUIRE_SCAN'],
        }

    for status in (400, 403, 404, 409, 413, 429, 500):
        def error_page(error):
            return render_template('error.html', error=error), error.code
        app.register_error_handler(status, error_page)
    return app
