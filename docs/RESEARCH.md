# Research register and advanced roadmap

## Sources used

| ID | Primary source | Project connection |
| --- | --- | --- |
| R1 | [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) | Layered validation, private storage, bounded uploads and scanning |
| R2 | [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) | Explicit memory-hard scrypt parameters |
| R3 | [NIST SP 800-218 SSDF Version 1.1](https://csrc.nist.gov/pubs/sp/800/218/final) | Security activities integrated into SDLC phases |
| R4 | [cryptography Fernet](https://cryptography.io/en/stable/fernet/) | Authenticated file encryption, key protection and size limitations |
| R5 | [PyOTP documentation](https://pyauth.github.io/pyotp/) | TOTP enrollment, replay prevention, throttling and passkey comparison |
| R6 | [Flask security considerations](https://flask.palletsprojects.com/en/stable/web-security/) | CSRF, cookies, request limits and browser headers |
| R7 | [Pillow Image reference](https://pillow.readthedocs.io/en/stable/reference/Image.html) | Image verification, loading, format detection and pixel-bound concerns |
| R8 | [ClamAV scanning documentation](https://docs.clamav.net/manual/Usage/Scanning.html) | Local scanner integration |
| R9 | [GitHub code scanning](https://docs.github.com/en/code-security/concepts/code-scanning/code-scanning) | Distinction between source analysis and runtime tests |
| R10 | [OWASP cryptographic storage](https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html) | Key-boundary and host-compromise threat discussion |

Accessed during 16–17 September 2026. Sources establish library behavior and general engineering guidance; they do not certify this application. The local requirements and implementation determine the actual accepted formats, quotas, routes and operating model.

## Implemented advanced features

The application includes image reconstruction, explicit MIME and signature consistency checks, a decompression-bomb boundary, authenticated file encryption, integrity-checked retrieval, optional TOTP with replay prevention, server-side session revocation and a per-user HMAC audit chain. Container and CI configuration are included. Their verification status is recorded separately from code availability.

## Extension proposals

### WebAuthn passkeys

Replace or supplement TOTP with origin-bound public-key credentials using a maintained WebAuthn library. Implement challenge creation, expiry, single-use verification, credential registration and multiple-device recovery. Test wrong origins, relying-party IDs, replayed challenges and recovery abuse. Unlike TOTP, passkeys can resist credential phishing through origin binding. This feature requires a stable HTTPS origin and a considered recovery policy.

### Asynchronous quarantine and content disarm

Add persistent states such as pending, scanning, accepted and rejected. Store new content in a separate non-public quarantine area and schedule bounded worker jobs. Downloads must deny all states other than accepted. Add format-specific content disarm and reconstruction before enabling PDFs or Office documents. Test scanner downtime, duplicate jobs, retries, crashes and large compressed structures. A background queue alone is not a security control without a fail-closed state machine.

### External key management

Generate a per-file data key and wrap it with a key manager. Record key version identifiers, scope service permissions and support rotation. Verify that backups can be restored using approved key versions and that key-manager failure never exposes plaintext. This reduces dependence on a single local key file but does not remove the application's authorization responsibility.

### External audit checkpoints

Periodically commit chain-head values to an independently protected append-only store. Verify checkpoints during audits to detect final-suffix truncation. Test missing, rolled-back and inconsistent checkpoints. A blockchain is unnecessary unless the project defines independent mutually distrustful participants and can justify its operational cost.

### Anomaly detection

Analyze aggregate counts such as repeated upload rejection, login failure rates and unusual download volume. Begin with explainable rules. If an ML model is added, define a labeled dataset, train/test separation, precision, recall, false-positive rate and privacy boundaries. Do not label a file malware-free from a filename classifier or invent model accuracy without evaluation.

### Scale and account lifecycle

Add PostgreSQL migrations, a shared rate limiter, a global capacity policy, invitations or moderated signup, recovery codes, credential changes, retention controls and server-side audit pagination. Validate multi-instance concurrency and recovery before claiming production scale.

## Document scanning with OpenCV

At upload, select Scan a document photo with OpenCV for a PNG or JPEG. The option detects a page, corrects perspective and enhances grayscale contrast. When no boundary is detected, it enhances the full frame and explains the fallback. It does not perform OCR or antivirus detection. Save the original locally if you need it: the vault stores the processed result.

Implementation references: OpenCV geometric transformations, https://docs.opencv.org/4.x/da/d6e/tutorial_py_geometric_transformations.html and histogram equalization/CLAHE, https://docs.opencv.org/4.x/d5/daf/tutorial_py_histogram_equalization.html (accessed 20 September 2026).
