# Secure File Upload System

A working Flask application for a cybersecurity academic project. The interface is called **SecureVault**. It provides private file upload, validation, normalization, encryption, access control, optional authenticator-based 2FA, and tamper-evident activity history.

## Continue in a new AI conversation

Read [AI_README.md](AI_README.md) for the ready-to-paste continuation prompt, source map, verified test evidence, college requirements and remaining deliverables. Open the project folder in the new conversation or provide its source alongside that handoff file.

## Start on Windows

Install Python 3.12 or newer, then open PowerShell in this folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Visit **http://127.0.0.1:5000**, create an account, and upload a TXT, PNG or JPEG file. No default account or password is shipped. Passwords must be 12–128 characters. Keep the terminal running. Press Ctrl+C to stop.

On Linux/macOS: `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`, then `.venv/bin/python run.py`.

## Security features

| Layer | Implemented behavior |
| --- | --- |
| Filename | Single allowlisted extension, restricted characters, bounded length, random storage ID |
| MIME | Declared MIME checked against extension; absent/generic binary MIME requires content validation |
| Content | PNG/JPEG magic bytes, Pillow format detection and full decoding; strict UTF-8 text validation |
| Normalization | Re-encode images, clear metadata, remove EXIF/GPS and trailing bytes; normalized file is downloaded |
| Resource limits | 5 MiB per file, 16 megapixels per image, 50 MiB and 200 files per account, bounded multipart request |
| Authentication | Salted scrypt password hashing; optional TOTP with replay protection and encrypted secrets |
| Sessions | Signed HttpOnly cookies, server-side revocation, 30-minute absolute lifetime, sign out all devices |
| Authorization | Owner checked for private downloads, previews and deletion; explicit bearer-code redemption for recipients |
| Sharing | Single-use, 15-minute codes with 96-bit randomness, hashed storage and owner revocation |
| Storage | Fernet authenticated encryption; SHA-256 of normalized plaintext checked on download |
| Antivirus | Optional local ClamAV adapter; configured scanner failure rejects uploads; required mode blocks absent scanner |
| Web controls | CSRF protection, parameterized SQL, escaped templates, restrictive CSP and security headers |
| Audit | Per-account HMAC chain detects event edits and interior deletion; latest 100 events displayed |
| Delivery | Waitress server, Docker configuration, pytest, GitHub Actions, Bandit and dependency-audit workflow |

**Important scope:** this is a tested academic application, not a certification of security. Antivirus is **not installed or enabled by default**. PDF, Office files, SVG, archives and executables are intentionally unsupported. See [security limitations](docs/SECURITY.md).

## Documentation

- [Project synopsis](docs/SYNOPSIS.md)
- [Full report including SRS and SDLC](docs/PROJECT_REPORT.md)
- [Architecture and diagrams](docs/DIAGRAMS.md)
- [Security model and limitations](docs/SECURITY.md)
- [Deployment and backup guide](docs/DEPLOYMENT.md)
- [Test plan and execution evidence](docs/TESTING.md)
- [Demonstration and viva guide](docs/DEMO_AND_VIVA.md)
- [Research sources and advanced roadmap](docs/RESEARCH.md)

Editable Word versions are generated in `docs/` by `scripts/build_documents.py`. Replace student, guide and institution placeholders before submission. The report describes actual implementation and labels future work separately.

## Run tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q --junitxml=docs/test-results.xml
```

Tests create isolated temporary databases and do not use the live vault. Scanner tests use controlled return codes; they do not claim that a real ClamAV installation was tested.

## Docker

```sh
docker compose up --build -d
docker compose logs -f
docker compose down
```

The named volume retains the database and encryption keys. **Do not run `docker compose down -v` unless you intend to destroy all data.** Docker Desktop must be running. Container execution is a separate deployment check; see the recorded status in the testing guide.

## Data and configuration

`instance/` is created on first startup. It contains `vault.sqlite3`, three private key files and encrypted blobs. Never commit or publicly serve it. Back up keys and data together. Losing `encryption.key` makes file contents and TOTP secrets unrecoverable.

`.env.example` describes environment variables. The app does not automatically read `.env`. See `docs/DEPLOYMENT.md` for PowerShell examples, antivirus mode and HTTPS configuration.

## Repository

Prepared for [abhishekk-y/Secure-File-Upload-System](https://github.com/abhishekk-y/Secure-File-Upload-System). Source files are local; publishing requires authenticated GitHub access. No remote publication is implied by this README.
