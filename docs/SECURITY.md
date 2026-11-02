# Security design and limitations

## Trust model

Treat clients, uploaded bytes, filenames and declared MIME types as untrusted. Trust the configured Python runtime, dependencies, operating system, private data directory and the operator. A malicious authenticated user must not access another user's file, overwrite server paths or bypass upload controls.

## Upload pipeline

1. Enforce HTTP request and multipart field/part limits.
2. Require an authenticated, unexpired, unrevoked session and a valid CSRF token.
3. Apply per-IP rate limits.
4. Accept a bounded simple basename with exactly one supported extension (TXT, PNG, JPEG, PDF, DOCX, CSV, HTML, XML or restricted SVG). Storage never uses that basename.
5. Read at most 5 MiB plus one byte; reject empty or oversized content.
6. Compare the extension to the declared MIME. Empty or `application/octet-stream` MIME is accepted only when subsequent content checks pass. A specific conflicting MIME is rejected.
7. For PNG require `89 50 4E 47 0D 0A 1A 0A`; for JPEG require `FF D8 FF`. Then compare the parser's format, enforce 16 megapixels, verify structure and fully decode. Signatures alone are insufficient.
8. Re-encode images after clearing metadata. This removes EXIF/GPS, comments, embedded metadata and trailing content. The original bytes are not retained. JPEG may be recompressed; PNG is converted to RGBA; animation is flattened to the decoded first frame.
9. For TXT require valid UTF-8 and reject C0 control characters other than tab, carriage return and line feed. There is no universal TXT magic value. Plain text is not classified as malware-free.
10. ClamAV is required by default. Scan the original and, when changed, the normalized bytes with a 30-second timeout. Detection, other errors, timeouts and missing executable reject the upload. An operator can explicitly change the requirement for a local test; this must not be presented as a scanned upload.
11. Acquire a SQLite write transaction, check the 500,000,000-byte (500 MB decimal) and 200-file quotas, create a random 128-bit storage ID, encrypt and persist normalized content, and write metadata. Roll back and remove the blob on ordinary storage/database failure.
12. Append an HMAC-linked audit event. Return a human-readable result.

Temporary scanning files contain plaintext inside the private data directory and are removed in a `finally` block. An abrupt process termination may leave a temporary file; operational cleanup is required. Operating-system swap and filesystem journaling are outside application-level encryption guarantees.

## Cryptographic choices

Passwords use salted scrypt with N=32768, r=8, p=3. SHA-256 is used for file fingerprints, not password storage. Fernet uses AES-128-CBC and HMAC-SHA-256 through the maintained cryptography library. It is authenticated encryption, **not AES-256 and not end-to-end encryption**. The server holds the key and can decrypt files. The same encryption key protects TOTP secrets. Session signing and audit authentication use separate keys.

Three persistent keys are generated on first startup. Linux file mode 0600 is requested; Windows installs additionally require NTFS directory permissions. If the host or key files are compromised, file encryption cannot protect against that attacker. Moving keys into an independently controlled secret manager and adding key rotation are future improvements.

## Sessions and MFA

The browser receives a signed Flask cookie with HttpOnly and SameSite=Lax; Secure is enabled by `APP_HTTPS=1`. A random session token is hashed in the server-side `sessions` table. Every request checks it against a 30-minute absolute expiry. Logout revokes the current server record. All-device logout deletes all session records for that user. Login replaces the current token. Signed-cookie contents are readable by the browser and contain no plaintext TOTP secret.

TOTP enrollment requires a password and code confirmation. Secrets and QR codes are generated locally; no QR web service receives them. Successful codes update the highest accepted time step atomically to reject replay. Sign-in accepts the current or adjacent 30-second window. MFA enrollment revokes other existing sessions. This academic version has no recovery codes, password reset or identity-recovery process. TOTP is susceptible to real-time phishing; passkeys are a proposed extension.

## Audit integrity

Each user has a separate HMAC-SHA-256 event chain using a private audit key. The MAC includes the prior MAC, row ID, owner ID, action, detail and timestamp. Audit insertion is serialized in a transaction. The activity page verifies the entire retained account history and displays the newest 100 records.

Edits to authenticated fields and deletion of interior records are detected. A database administrator who cannot access the audit key cannot simply recompute valid MACs. However, deletion of the final suffix or entire chain is not detected without an independent checkpoint; possession of the audit key allows forgery. This is not an immutable or legally nonrepudiable ledger. Preexisting unsigned events are reported as unverified rather than silently blessed. External checkpoint storage is future work.

## Threat assessment

| Threat | Implemented mitigation | Residual limitation |
| --- | --- | --- |
| Traversal and overwrite | Strict basename, random internal ID, owner-bound lookup | Host filesystem must remain trusted |
| Executable disguised as image | MIME comparison, signature, decoder and re-encoding | Parser vulnerabilities require dependency updates |
| Decompression bomb | Pixel cap, Pillow bomb warnings treated as errors | Concurrent image work still uses memory |
| Cross-account access | Owner predicate on list/download/delete | Operator can read database and keys |
| CSRF | Flask-WTF token on all state-changing routes | XSS or stolen session compromises need separate controls |
| SQL injection | Parameterized user-input queries | Dynamic migration SQL uses fixed developer-owned constants |
| Stored HTML/script | Escaped templates, restricted names, attachment downloads, CSP | Downloaded text can be dangerous if manually executed |
| Password guessing | scrypt and per-IP throttling | Distributed attacks and account enumeration need further work |
| TOTP replay | Atomic last-step update | TOTP does not provide phishing resistance |
| Blob corruption | Fernet authentication and SHA-256 check | Missing files are unavailable until restored |
| Database log edits | Per-user HMAC chain | Truncation and key compromise need external checkpoints |
| Storage exhaustion | 5 MiB per-file, 500 MB per-account and 200-file limits | Total host capacity remains outside per-account quotas |

## Scale and verification boundary

This implementation is designed and tested as a small, single-process academic application. Its in-memory rate limiter resets on restart and does not coordinate across instances. No external penetration test, load test, formal accessibility certification or compliance assessment has been performed.

## OpenCV document scanner

The optional upload checkbox processes a validated PNG/JPEG as a document photo. OpenCV downsamples to a maximum 2000-pixel side, detects candidate page edges, applies a perspective transform to a convex four-corner page and improves grayscale contrast with CLAHE. If no clear boundary is found, the whole image is enhanced without cropping, and the user receives that result explicitly. Images under 64 pixels per side are rejected for this option. The resulting bytes still pass antivirus policy, size/quota checks and encrypted storage. OpenCV is image cleanup; OCR is a separate Tesseract check. Detection can crop the wrong quadrilateral; inspect the result and retain your original separately. Scanned output replaces the upload's stored representation.

## Local signatures and text checks

YARA-X compiles local rules in `app/rules/` and checks the original upload. A match blocks the upload and the rule name is saved to the owner's inspection report. Rule compilation or scanning errors also reject the upload. The rules cover recognizable script and macro patterns and the harmless EICAR test signature. This small ruleset supplements ClamAV; it is not a complete malware database and no-match does not mean clean.

Tesseract OCR is attempted for PNG/JPEG and PDF pages when installed natively. `TESSERACT_CMD` selects its executable and `OCR_LANGUAGE` selects installed trained data. PDFium renders at most ten pages; each Tesseract call has a timeout. Extracted text is transient and feeds the existing DLP patterns; OCR output is not saved. Reports retain OCR status and character count only. A missing engine or parser failure is reported as unavailable without exposing parser details. OCR can miss or misread content, especially handwriting, low contrast or unusual layouts. PDFium currently runs in the application process; page and file bounds reduce workload but do not create a sandbox. Until PDF rendering is moved to a separately restricted worker, use synthetic documents for demonstrations and keep the feature set within its documented academic scope.

## Processing status and inspection reports

Every new upload records document processing separately from antivirus. The vault labels content validation, OpenCV processing and antivirus explicitly. Existing uploads without a recorded processing field are marked as older records rather than assigned an invented result. Owners can download a JSON inspection report from file details. Generation verifies the encrypted blob and SHA-256 before reporting integrity. The report includes MIME, normalized size, upload time, processing outcome and antivirus state; it is not an independent security certificate.

## Advanced-format policy

The README implementation guide and this document specify PDF, DOCX, CSV and markup reconstruction behavior, worker boundaries, DLP rules, YARA-X signatures and the local denylist. Generic archives and executables remain rejected. A missing parser or worker failure rejects the upload. No commercial CDR engine or dynamic sandbox is claimed. The owner-only security report displays original/stored hashes and individual results.
