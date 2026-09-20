# Demonstration and viva guide

## Ten-minute demonstration

1. Start the application and explain the permitted formats and limits. Register two test accounts with fictional data.
2. Sign into the first account and upload a small TXT file. Show its displayed size, scan status and SHA-256 fingerprint.
3. Download the file and verify that the text matches. Explain that stored bytes are encrypted while the database holds metadata.
4. Upload a PNG or JPEG with harmless test EXIF metadata. Download the normalized image and explain why the fingerprint and bytes can change.
5. Demonstrate rejection of a fake image, MIME mismatch, double extension and oversized file using the automated test evidence where the browser cannot construct the request directly.
6. Sign into the second account and explain that copying a file identifier does not grant ownership. Show the cross-account test evidence.
7. Open Activity and show successful/rejected operations and the audit-chain status. Use an isolated test database for tampering demonstrations; never corrupt the live vault.
8. Open Security, enroll an authenticator and confirm a code. Explain that enrollment consumes the code, so wait for a fresh time step before testing another sensitive operation.
9. Demonstrate sign-out and all-device revocation with test accounts. Do not enable MFA on a valuable account without an authenticator backup.
10. Show the test summary, SDLC traceability, security limitations and future roadmap. State whether the real antivirus scanner is configured.

## Viva questions and answers

### Why are extension and MIME checks insufficient?

Both can be chosen by a client. They are consistency signals, not proof of file structure. The server also checks signatures and decodes supported images.

### What are magic bytes?

They are characteristic bytes in a file's binary structure. This project checks the PNG signature and the JPEG opening bytes, then validates using Pillow. A forged signature can still surround invalid content.

### How is TXT identified?

There is no universal text magic number. The project accepts valid UTF-8 without disallowed C0 control bytes and serves downloads as attachments.

### What is MIME?

Multipurpose Internet Mail Extensions media types describe content, such as image/png or text/plain. A multipart upload contains a client-declared type; the app compares it to the expected type but independently validates content.

### How does metadata stripping work?

The server decodes the image into pixels, converts it to an allowed mode, clears metadata and writes a new image. EXIF and GPS tags from the original are not copied. JPEG may be recompressed and image animation is flattened.

### Why encrypt and also compute a hash?

Fernet supplies confidentiality and authenticated integrity. SHA-256 additionally provides a stable fingerprint of the normalized file for comparison and an explicit consistency check. Hashing is not encryption.

### Is Fernet AES-256?

No. Fernet uses AES-128-CBC with HMAC-SHA-256 through a maintained library. Its encoded key contains material for encryption and authentication. The project must not mislabel it as AES-256.

### Is this end-to-end encrypted?

No. The server holds the key, processes plaintext and can decrypt content. It provides application-managed encryption at rest.

### Why use scrypt for passwords?

It is a salted, memory-hard password hashing function. This implementation explicitly uses N=32768, r=8 and p=3. A fast SHA-256 hash would make offline guessing much cheaper.

### What prevents IDOR?

Every download and delete query includes both the file ID and the authenticated owner's ID. Random IDs are an additional precaution but do not replace authorization.

### How do CSRF and XSS protections differ?

CSRF tokens prevent a different site from authorizing a state-changing request through a user's session. Escaped templates and CSP reduce script-injection exposure. They address different attack paths.

### Why store sessions on the server?

A signed cookie alone can remain cryptographically valid after logout if copied. The server token record can be revoked, making subsequent use fail immediately.

### How is TOTP replay prevented?

The server atomically records the highest accepted time step and requires a newer one. A code cannot be consumed twice for the same account step.

### Is the activity log immutable?

No. It is HMAC-linked and detects changes to retained records. Removing the final suffix requires an independently stored checkpoint to detect, and an attacker holding the audit key could forge records.

### What is fail-closed scanning?

If scanning is configured, detection, an error or a timeout rejects the upload. Required mode also rejects missing scanner configuration. The default demo mode is explicitly labeled unscanned.

### Why not support all file formats?

Different formats require different parsers and policies. Restricting the initial format set keeps the attack surface and acceptance tests manageable. PDF and Office support need a separate content-disarm and quarantine design.

### Which SDLC model is used?

An iterative secure SDLC. Planning, requirements, design, implementation, testing, deployment and maintenance each produce reviewable artifacts and include security tasks.

### What is the difference between verification and validation?

Verification checks whether implementation satisfies requirements. Validation checks whether the resulting workflow meets the intended user's need. Automated policy tests and browser demonstrations contribute different evidence.

### What are the main remaining risks?

Host/key compromise, parser vulnerabilities, distributed abuse, missing recovery, optional antivirus, audit truncation and operational backup failures. These are documented rather than hidden.

## Submission checklist

- Replace student, enrollment, college, guide and academic-year placeholders.
- Add only genuine institutional signatures, declarations and acknowledgements.
- Review the code and explain every security feature you demonstrate.
- Capture final screenshots from the version submitted.
- Include the synopsis, report, diagram sources, test evidence and setup instructions.
- Keep keys, live databases, uploaded files and local environments out of GitHub.
- Follow the institution's assistance-disclosure and reference-format requirements.
