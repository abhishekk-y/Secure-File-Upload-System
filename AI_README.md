# SecureVault — AI conversation handoff

Last checked: 20 September 2026. This file records project context for continuing in a new conversation. It is not evidence that pending work has been completed. Recheck the working tree and runtime before changing or making claims about them.

## Start a new conversation

Open this project folder in the new conversation and paste:

> Continue my Secure File Upload System (SecureVault) project. Read AI_README.md first, then inspect the current source and test evidence. Finish the remaining implementation checks, college documentation, presentation and README, and publish the finished files to my GitHub repository as previously requested. Preserve the working security features and my design requirements. Do not add the removed six-week schedule. Distinguish implemented features, verified results and future work. Work through the outstanding tasks rather than only proposing a plan.

If the new conversation cannot access the folder, attach this file and a source archive excluding private data, keys, environments and caches. This file alone does not contain the application. The new assistant must establish repository access before editing or publishing.

## Project and requested outcome

- Academic cybersecurity project: **Secure File Upload System**; interface name: **SecureVault**.
- Local workspace: `D:\CyberSECProject`.
- Intended GitHub repository: https://github.com/abhishekk-y/Secure-File-Upload-System
- User has requested a fully working demonstration, synopsis, complete report, user manual, presentation, polished README and GitHub publication.
- No college-mandated technology stack. Current implementation uses Python, Flask, SQLite, server-rendered Jinja, CSS and JavaScript.
- User wants original design inspired by file-management interfaces: neobrutalist borders and offset shadows, neoclassical/editorial typography on the landing page, restrained workspace cards/tables, animated arrows and accessible motion.
- Sharing by code must work. Security must include MIME checks, magic-byte checks, size constraints, metadata stripping and advanced controls with honest limitations.
- README should have proper headings, original icons, images and diagrams; **no emoji**.
- **Remove and do not restore the entire six-week proposed schedule.** A dependency-based development sequence can describe SDLC without a fabricated calendar.
- Student, institution, department and guide details have not been provided. Keep explicit placeholders; never invent signatures, awards or approvals.

## Current implementation

The source contains the following features; the latest recorded automated run is described separately below.

| Area | Behavior |
| --- | --- |
| Accounts | Registration, salted scrypt passwords, login/logout, optional authenticator TOTP with replay checks |
| Sessions | Signed HttpOnly/SameSite cookies, server-side revocation, 30-minute absolute expiry, revoke other sessions |
| Upload | TXT, PNG, JPG/JPEG allowlist; restricted basename and one extension; MIME consistency and content validation |
| Resource bounds | 5 MiB/file, 16 megapixels/image, 50 MiB and 200 files/account |
| Normalization | Pillow decoding and re-encoding; clear image metadata, strip EXIF/GPS and trailing bytes; strict UTF-8 text |
| Storage | Random identifiers, private encrypted Fernet blobs, SQLite metadata, SHA-256 plaintext integrity checks |
| Access | Owner-only download, image preview and delete; explicit bearer-code access for recipients |
| Sharing | Random 96-bit code; only its hash stored; 15-minute expiry; single use; owner revocation; atomic redemption |
| Audit | Per-user HMAC chain, verification of retained history, latest 100 events displayed |
| Web controls | CSRF, rate limits, parameterized SQL, escaped templates, CSP and security headers |
| Scanner | Optional ClamAV subprocess adapter; scanner errors reject uploads; required mode blocks missing scanner |
| Interface | Public landing, login/register, vault, search/type filters, upload dialog/progress, image details, shared codes, receive, activity and security pages |

Fernet uses AES-128-CBC with HMAC-SHA256; do not call it AES-256 or end-to-end encryption. The application server holds decryption keys. Audit chaining cannot prove that a final suffix of records was not removed without an external checkpoint. Sharing codes are bearer credentials and are consumed before successful network delivery is guaranteed. In-memory rate limiting is intended for the current single-process deployment. PDF, Office, SVG, archives and executables are unsupported. No TOTP recovery workflow is implemented.

## Source map

```text
app/
  __init__.py             App factory, database, security pipeline and routes
  templates/             Jinja pages and original SVG icon macro
  static/
    design.css           Current active design system
    app.js               Dialogs, upload progress, filtering and copying
    mark.svg             Application mark
run.py                   Waitress entry point
tests/
  test_security.py       Authentication, upload and security regression tests
  test_sharing.py        Sharing, isolation, preview and concurrency tests
scripts/
  build_documents.py     Existing Markdown-to-DOCX/PDF generator
  start.ps1              Existing launcher; inspect before use
docs/                    Report sources, exports, figures and test evidence
.github/                 CI and dependency-update configuration
Dockerfile
compose.yaml
requirements.txt
requirements-dev.txt
.env.example
README.md
AI_README.md             This handoff
```

Older `style.css` and `theme.css` may remain unused; `base.html` loads `design.css`. Inspect references before cleanup. Routes include `/`, `/vault`, `/upload`, `/security`, `/activity`, `/shares`, `/receive`, `/files/<identity>/download`, `/files/<identity>/preview`, and owner share/delete actions.

## Run and verify

Portable Windows setup, with Python 3.12 installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Open http://127.0.0.1:5000 and register an account. No default credentials are shipped. Passwords require 12–128 characters. The server defaults to loopback; check `/health` before assuming an old server remains running.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q --junitxml=docs/test-results.xml
```

On the original machine, a bundled Python is available at `C:\Users\LENOVO\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`, with local packages in `.runtime`. Set `PYTHONPATH` to the absolute `.runtime` folder when using that fallback. These paths are machine-specific and must not become requirements for other users.

### Evidence and verification boundaries

- `docs/test-results.xml`: **49 tests, 0 failures, 0 errors, 0 skipped**, 272.530 seconds; recorded 17 September 2026. This is an existing result, not a new test run on the handoff date.
- Coverage includes upload rejection/normalization, encryption, ownership, CSRF, sessions, TOTP, audit tampering, quotas and sharing expiry/revocation/concurrent redemption.
- Scanner tests use controlled subprocess outcomes. A real ClamAV installation has **not** been verified.
- `docs/bandit-results.json` exists from an earlier scan; rerun after final code changes before claiming current scan status. Dependency-audit tooling was installed but its completed result is not established.
- Docker files exist; Docker Engine was unavailable during the previous check. Container deployment remains unverified.
- Current redesigned UI still needs browser inspection at desktop and mobile sizes and end-to-end interaction checks. Check mobile sign-out reachability and upload error handling.
- Synopsis PDF was visually checked in earlier work. The full report exports are outdated relative to the requested college arrangement and new sharing behavior.
- DOCX visual rendering was blocked by missing bundled LibreOffice. Do not label those exports visually verified. Prefer inspected PDF plus editable Markdown until rendering is resolved.

## College report requirements

The supplied arrangement requires:

1. Title page, Bonafide Certificate, Acknowledgement, Table of Contents, List of Figures, List of Tables, Abstract, Graphical Abstract, Abbreviations/Symbols.
2. Chapter 1: Introduction, client/need, contemporary issues, problem/task identification, development sequence and report organization.
3. Chapter 2: Literature survey, historical research progression, bibliometric analysis, existing solutions and relation to project goals.
4. Chapter 3: Design concepts/specifications, constraints, at least two alternative designs, comparison and selection, implementation flow/algorithms.
5. Chapter 4: Results, engineering tools, design diagrams, testing, interpretation and validation.
6. Chapter 5: Conclusion, future work and deviations.
7. Alphabetical author/year references, numbered appendices, pictured user manual and achievements supported by evidence.

Discuss economic, environmental, health, manufacturability, safety, professional, ethical, social, political and regulatory constraints where applicable; explain non-applicability instead of inventing effects.

Formatting: A4; black text; Times New Roman 12 body, justified, 1.5 spacing. Chapter title bold 16 centered; headings bold 14; subheadings bold 12; captions bold 10. Table captions above and figure captions below. Bonafide and one-page abstract use 14-point double spacing. Front matter uses lowercase Roman page numbers. Contents excludes title and certificate, includes other front matter; figure/table lists match captions. Cover is intended for thick white art paper with black printing.

Original supplied text, available only on the initial machine: `C:\Users\LENOVO\.codex\attachments\60e2466f-1a45-4382-bbca-c842d9a670d2\pasted-text.txt`. Consult it if accessible. The requirements above preserve the essential handoff context.

## Remaining work, in priority order

1. Inspect current app in a browser, resolve actual UX defects, and capture original screenshots using a clearly identified demonstration account without exposing secrets.
2. Reconcile documentation with implemented sharing and security boundaries. Rewrite `PROJECT_REPORT.md` into the supplied five-chapter arrangement. The existing report is an older structure.
3. Create `docs/TESTING.md`, currently missing despite its README link. Record actual test/scan/deployment outcomes, distinguishing mocked scanner checks from real antivirus.
4. Complete graphical abstract, architecture, upload/share sequence, database diagram, requirements-to-tests mapping and pictured user manual.
5. Finish literature review with verified primary sources. Bibliometric analysis should be explicitly limited to a small curated corpus with a reproducible source list and descriptive counts; do not invent global citation statistics.
6. Update the document generator to college formatting, regenerate synopsis/report, and visually inspect exported pages. Preserve removal of the weekly schedule.
7. Create an editable presentation and a viewable export covering problem, solution, uniqueness, research, stack, architecture, file tree, security pipeline, sharing, database, SDLC, actual results, live demo, limitations and references. Add speaker notes or a companion script. Presentation has not yet been created.
8. Polish the main README with original header/icon assets, actual screenshots, diagrams, quickstart and complete artifact links. Remove stale statements; do not advertise unverified functionality.
9. Run checks appropriate to final changes, inspect staged files for secrets, commit and publish to the intended repository. Verify the remote commit before reporting publication.

## Research starting points

Use primary documentation and verify current details when researching. Existing discussion and sources are in `docs/RESEARCH.md`.

- OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
- OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- NIST SP 800-218, Secure Software Development Framework (2022): https://csrc.nist.gov/pubs/sp/800/218/final
- Cryptography Fernet documentation: https://cryptography.io/en/stable/fernet/
- Flask web security: https://flask.palletsprojects.com/en/stable/web-security/
- Pillow Image reference: https://pillow.readthedocs.io/en/stable/reference/Image.html
- PyOTP documentation: https://pyauth.github.io/pyotp/
- ClamAV scanning documentation: https://docs.clamav.net/manual/Usage/Scanning.html
- Eian et al. (2020), Integration of Security Modules in Software Development Lifecycle Phases: https://arxiv.org/abs/2012.05540
- Kudriavtseva and Gadyatskaya (2022), Secure Software Development Methodologies: A Multivocal Literature Review: https://arxiv.org/abs/2211.16987
- Neef and Oudeh (2024), Bringing UFUs Back into the Air With FUEL: https://arxiv.org/abs/2405.16619

These sources inform design; their experimental results are not results of SecureVault. Project uniqueness is the integrated educational workflow and visible security controls, not a claim of inventing new cryptography or upload defenses.

## Git and private data

At this check the project files are untracked in a local Git repository; no publication has been verified. Inspect `git status`, history and remote before proceeding because a later conversation may have changed them. The user previously authorized publishing project deliverables to the intended GitHub repository.

Never commit `instance/`, private key files, databases, uploaded content, `.env`, `.runtime/`, virtual environments or test caches. `instance/` contains the database, encryption/session/audit keys and encrypted blobs. Back up keys and data together privately. Do not delete or regenerate live keys to solve startup problems. Check `.gitignore` and the staged diff before publishing. Do not include third-party inspiration screenshots as original project assets.

Update this handoff when work changes: record verified outcomes, remaining tasks and exact artifact locations. A future assistant should be able to continue without relying on inaccessible conversation history.
