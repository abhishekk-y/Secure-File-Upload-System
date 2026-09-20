# Deployment and operations

## Local setup

Use Python 3.12 on Windows, macOS or Linux. Create a virtual environment and install `requirements.txt`, then run `run.py`. Windows commands are in the README. The service listens on loopback port 5000 by default and is served by Waitress. Create your own account; the application has no seeded production login.

If Python opens the Microsoft Store, install a real Python runtime and use the `py -3.12` launcher. If port 5000 is occupied, use `$env:PORT='5001'` before starting. If the browser says the connection failed, confirm the process is still running and read its terminal output.

## Environment configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| HOST | 127.0.0.1 | Bind address; keep loopback for local demonstration |
| PORT | 5000 | HTTP port |
| DATA_DIR | Project instance directory | Absolute private data path |
| APP_HTTPS | 0 | Set 1 when browser access uses HTTPS; enables Secure cookie and HSTS |
| CLAMSCAN_PATH | Empty | Absolute executable path for a working local ClamAV scanner |
| REQUIRE_SCAN | 0 | Set 1 to block uploads unless scanning can complete |
| RATELIMIT_STORAGE_URI | memory:// | Single-process in-memory limiter or configured supported backend |

The app does not parse `.env`. Set environment variables in PowerShell, a process manager or a Compose environment configuration.

```powershell
$env:DATA_DIR = 'D:\SecureVaultData'
$env:PORT = '5000'
.\.venv\Scripts\python.exe run.py
```

Choose and protect the data directory before startup. Never use a directory served by another website. On Windows, limit NTFS access to the operator and service account. On Linux, use a dedicated service account and directory mode 0700; generated key files request mode 0600. Directory permissions matter because SQLite contains usernames, filenames, hashes and audit details in plaintext.

## Antivirus mode

Install ClamAV from its official distribution, configure signature storage and update signatures with its supported update mechanism. Verify the scanner independently before configuring the application.

```powershell
$env:CLAMSCAN_PATH = 'C:\Program Files\ClamAV\clamscan.exe'
$env:REQUIRE_SCAN = '1'
.\.venv\Scripts\python.exe run.py
```

The executable path must be real. An installed binary without a working signature database is insufficient. The app scans normalized bytes in a temporary private file, waits at most 30 seconds and rejects scanner failures. The supplied Docker image does not include ClamAV; add and validate it in a dedicated deployment variant before enabling required mode in a container. Do not point CLAMSCAN_PATH to a script that always returns success.

For a real scanner acceptance test, use approved harmless antivirus test material in an isolated environment following the scanner vendor's instructions, verify detection, then verify the application rejects it. This was not executed by the controlled adapter tests.

## HTTPS and reverse proxy

For remote use, keep Waitress behind a trusted TLS proxy. Terminate HTTPS at the proxy, enable `APP_HTTPS=1`, and forward only to the private application port. Because Flask-WTF checks secure-request referers, configure the trusted proxy to communicate the external scheme correctly and add narrowly configured `ProxyFix` only for the exact trusted proxy topology. Do not blindly trust user-supplied X-Forwarded headers. Test CSRF and secure cookies on the final domain before opening access.

No reverse-proxy trust is enabled by default. Without explicit trusted client-IP handling, per-IP rate limiting may aggregate users behind the proxy; configure and test that behavior before deployment. Shared Redis limiting requires installing the supported Flask-Limiter Redis extra and protecting the Redis service. Do not assume `memory://` coordinates multiple workers or hosts.

## Docker operations

Start Docker Desktop or your Docker Engine before running `docker compose up --build -d`. The supplied compose configuration publishes only to localhost and keeps `/data` in a named volume. It runs the container with no added Linux capabilities, no-new-privileges, a read-only root filesystem and resource limits. Confirm container health and a complete upload/download workflow after building.

`docker compose down` stops the service without deleting the named volume. Deleting that volume destroys the database, blobs and keys. Container runtime execution was not verified on the development host because its Docker Engine was not running; the native Waitress workflow is the verified local execution path.

## Backup and restore procedure

1. Notify local users and stop the application process.
2. Copy the complete DATA_DIR, including SQLite database and any WAL/SHM files, encrypted vault and all three keys, into a protected backup location.
3. Encrypt or access-restrict the backup. A ciphertext backup containing its decryption key needs protection as a whole.
4. Restore into a separate private directory; do not overwrite the live directory for a rehearsal.
5. Set DATA_DIR to the restored location and start the app on a different loopback port.
6. Sign in, download a known test file and verify its expected content/hash. Check audit history.
7. Record the backup date, restored version and result. Remove rehearsal data according to local policy.

This is a manual consistent-snapshot approach for the small project. Automated online backups and key rotation require additional design. No successful backup should be assumed until a restore has been tested.

## Incident response

If stored content fails integrity checks, stop distributing the affected file, preserve relevant evidence and restore from a known-good backup. If a credential is suspected compromised, revoke all sessions and follow an operator recovery process. If host keys are compromised, isolate the host, assess all stored data and MFA secrets as potentially exposed, and perform a planned rotation/re-enrollment. The app does not automate these incident procedures.

## Repository publication

Before committing, confirm `instance/`, `.runtime/`, `.venv/`, test temporary directories and `.env` are ignored. Never upload real user files or keys. Add the source to the intended new GitHub repository after verifying its remote. GitHub Actions and Dependabot run only once the configuration is published and enabled. No cloud endpoint or successful remote pipeline is implied by local checks.
