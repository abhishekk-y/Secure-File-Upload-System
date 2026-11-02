# SecureVault handoff for a future coding session

## Project identity

SecureVault is an academic secure-file-upload and private-vault application. The current source is in this repository; the intended GitHub remote is `https://github.com/abhishekk-y/Secure-File-Upload-System.git`. The UI has an original editorial style with neo-brutalist details and restrained neoclassical typography.

Read [README.md](README.md) first. Then use [SECURITY.md](docs/SECURITY.md), [SYNOPSIS.md](docs/SYNOPSIS.md), [DIAGRAMS.md](docs/DIAGRAMS.md), [TESTING.md](docs/TESTING.md), [RESEARCH.md](docs/RESEARCH.md) and [DEMO_AND_VIVA.md](docs/DEMO_AND_VIVA.md) as implementation context. The requested detailed academic project report is the next writing task.

## Current implementation map

| Path | Responsibility |
| --- | --- |
| `app/__init__.py` | Flask app factory, account/session routes, database, quotas, upload/download/share policy, encryption and audit events |
| `app/security_engines.py` | Format policy, YARA-X, ClamAV adapter, Tesseract OCR adapter, DLP and hash denylist |
| `app/content_worker.py` | Time-bounded reconstruction of PDF, DOCX, CSV, HTML, XML and SVG |
| `app/document_scanner.py` | Optional OpenCV page detection, perspective correction and image cleanup |
| `app/templates/` | Server-rendered pages and owner inspection report |
| `app/static/` | CSS, JavaScript and original SVG logo |
| `app/rules/` | Readable local YARA-X signatures |
| `tests/` | Account, security, format, sharing, OCR wiring and image-scanner cases |
| `samples/` | Synthetic safe demonstration files |
| `docs/` | Synopsis, presentation, research, design, screenshots and verification notes |

## Upload pipeline

1. Require authenticated session and CSRF token; apply request and rate limits.
2. Enforce filename, extension/MIME agreement, size and supported-format constraints.
3. Inspect original bytes with the local hash policy, executable indicators, YARA-X, and ClamAV. ClamAV is required by default; missing scanner or scan failure rejects upload.
4. Reconstruct supported documents to reduced-feature output. Run OpenCV only when explicitly selected for a PNG/JPEG document photo.
5. Attempt Tesseract OCR for PNG/JPEG and bounded PDF pages when native Tesseract is installed. OCR text is transient and feeds the existing DLP checks.
6. Reject likely credential findings. Prevent sharing when required checks are unavailable or supported personal-data findings are present.
7. Re-scan changed output with ClamAV, enforce account limits, encrypt the accepted bytes and save metadata.
8. Check owner authorization and stored integrity again on preview/download/report; shares are hashed, expiring, revocable and single-use.

## Honest feature boundaries

- Per-file maximum: 50 MiB. Per-account quota: 500,000,000 bytes (500 MB decimal), 200 files. Self-registration defaults to five accounts.
- Supported formats: TXT, PNG/JPEG, PDF, DOCX, CSV, HTML, XML and restricted SVG. ZIP and executable formats are rejected.
- Local rules and pattern checks provide indicators only. A YARA no-match or ClamAV clean result is not a universal malware-free guarantee.
- Fernet is server-side encryption at rest; the server retains the key. The app does not provide end-to-end encryption.
- Process separation has deadlines and input/output bounds but is not a hardened OS sandbox. PDF OCR rendering remains in the application process.
- Commercial Deep CDR, multiple commercial antivirus engines and dynamic sandbox execution are not included.
- Tesseract is not installed in the current Windows development environment. The OCR-to-DLP handoff is covered with controlled test responses; native OCR execution needs its own acceptance check when Tesseract is present.
- ClamAV 1.5.4 and its local signatures were used for a benign fixture and custom local-rule fixture. The EICAR scanner result was inconclusive (exit code 2) and must not be represented as passed.

## Latest verification snapshot

- Full regression suite: 93 passed, zero failures, in 65.70 seconds on 3 November 2026.
- Bandit: zero medium/high findings; seven low findings, including expected argument-list subprocess use with timeouts and an XML serializer import. Uploaded XML is parsed using `defusedxml`.
- Full dependency audit after the Pillow update: no known advisories in the resolved dependency graph at audit time. Use the committed JSON summary; rerun before a future release.
- Do not convert any of these checks into claims that the project is “unhackable,” certified, or independently penetration-tested.

## Working conventions

- Preserve private `instance/`, `.env`, `.runtime/`, `.venv/`, `.clamav/`, generated keys, databases and real uploaded files outside Git.
- Exclude root-level academic worksheets and student-specific temporary files unless the user explicitly asks to include them.
- Do not claim OCR ran natively unless the executable actually ran against the synthetic OCR sample.
- Keep the README aligned with code and current evidence; badges must not imply an unrun CI workflow or certification.
- The user requested the README/source handoff first, then the academic report.
