# Testing and validation

## Recorded automated execution

The committed JUnit file is the machine-readable evidence. The run on 17 September 2026 completed 49 tests with zero failures, errors or skips in 272.530 seconds. It is a regression suite, not proof of absence of vulnerabilities. A subsequent run replaces that evidence when implementation changes require it.

## Requirements and verification matrix

| Requirement | Verification | Expected behavior |
| --- | --- | --- |
| Account access | Registration, password, session and TOTP tests | Invalid credentials and replayed OTPs rejected |
| File allowlist | Extension, MIME, signature and UTF-8 cases | Mismatched or malformed input rejected |
| Normalization | EXIF, trailing-content and pixel-limit fixtures | Metadata removed; excessive dimensions rejected |
| Private storage | Ciphertext and integrity tests | Plaintext not stored as the vault blob; corruption rejected |
| Authorization | Two independently authenticated accounts | Another account cannot download, preview, delete or share a file |
| Quotas | Size, total bytes and file-count boundaries | Over-limit requests rejected |
| CSRF | Missing and invalid token requests | State-changing request rejected |
| Audit | Event field changes and interior deletion | Verification reports invalid history |
| Sharing | Expiry, revocation, deletion and simultaneous redemption | At most one successful redemption; invalid codes rejected |
| Antivirus adapter | Mocked detection, timeout and failures | Upload rejected when scanner fails or detects a threat |

## Static analysis

Bandit was executed on 20 September 2026 against `app` and `run.py`. Its JSON report records zero high, zero medium and two low severity findings concerning subprocess use. The adapter passes a fixed argument list without a shell, uses an operator-configured executable and sets a timeout. These controls explain the retained use; low findings are not silently suppressed. Re-run after backend changes.

## Browser demonstration checks

On 20 September 2026 the local Waitress server started on loopback, demo-account login succeeded, the vault displayed real files and a text file was uploaded through the actual browser form. The success notice and updated file count were observed. Screenshots in `docs/screenshots` are from demonstration data, not customer files. Responsive screenshots and further checks are recorded as they are completed.

## Repeat the suite

Create a virtual environment, install `requirements-dev.txt`, then run `python -m pytest -q --junitxml=docs/test-results.xml`. Run `python -m bandit -r app run.py -ll` and `python -m pip_audit -r requirements.txt` after installing those optional tools. CI performs these checks on pushes and pull requests; a local result does not imply a successful remote CI run.

## Boundaries

Real ClamAV scanning and Docker container execution have not been verified on this workstation. Scanner tests use controlled subprocess responses. Load testing, external penetration testing, multi-node deployment and formal accessibility certification are not claimed. No performance service-level objective is asserted from the regression runtime.
