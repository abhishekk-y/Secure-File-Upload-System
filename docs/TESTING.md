# Testing and verification record

This record reports evidence from the tested local source version. It is not a security certification, penetration-test report or proof that all vulnerabilities are absent.

## Latest regression execution

On **3 November 2026**, the full pytest suite completed with **94 passed, 0 failed** in **78.66 seconds**. The test cases cover account and session controls, CSRF, file allowlists, parser bounds, document reconstruction, image normalization, DLP decisions, YARA-X matches, scanner failure handling, encrypted storage, authorization, integrity, single-use sharing, OpenCV document processing and Tesseract path discovery.

Repeat the suite from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q --junitxml=docs/test-results.xml
```

The GitHub Actions workflow runs pytest, Bandit and pip-audit on pushes and pull requests. A local pass does not mean that the remote workflow has completed successfully.

## Verification summary

| Check | Result | Scope and boundary |
| --- | --- | --- |
| Functional/security regression tests | 94 passed, 0 failed | Defined automated cases; not exhaustive testing |
| Bandit static analysis | 0 high, 0 medium, 7 low findings | Low findings are subprocess import/call alerts and the XML output serializer import; untrusted XML input uses `defusedxml`; subprocesses use argument arrays and timeouts |
| pip-audit | No known advisories in the resolved dependency graph on 2 November 2026, after Pillow was updated to 13.0.0 | Advisories can be published later; rerun before a new release |
| ClamAV benign fixture | Passed with local ClamAV 1.5.4 and current-at-test signature database | Shows that the scanner ran on the fixture, not broad detection quality |
| ClamAV custom local signature fixture | Expected local rule signature detected | Controlled local integration fixture, not a commercial threat feed |
| EICAR scanner fixture | Inconclusive; ClamAV returned exit code 2 | Not counted as a successful detection check; the application rejects scanner errors |
| OCR-to-DLP wiring | Native Tesseract 5.5.3 recognized the synthetic OCR fixture; the real output reached DLP and was blocked without storing the matched value | One synthetic English image only; this does not measure OCR accuracy on varied documents |
| Browser review | Login, vault, upload dialog, report, MFA/session controls, sharing and receiving pages were observed | Screenshots are interface examples; current security verdicts must be demonstrated with fresh uploads |

## Requirements-to-test matrix

| Requirement | Test focus | Expected behavior |
| --- | --- | --- |
| Account access | Registration cap, password, sessions, MFA and replay | Invalid input and reused codes are denied |
| Upload allowlist | Extension, MIME, signatures, UTF-8 and malformed formats | Unsupported or inconsistent bytes are rejected |
| Normalization | Image metadata, PDF/DOCX reconstruction, markup and CSV cases | Stored representation follows the format policy |
| Resource bounds | File size, image pixels, PDF pages, parser output and worker timeout | Over-limit work is rejected safely |
| Private storage | Ciphertext, hash and tampered blob | Plaintext is not the stored blob; integrity failure blocks retrieval |
| Authorization | Multiple accounts and crafted identifiers | Another account cannot read, delete or share a file |
| CSRF | Missing or invalid token on state-changing requests | Request is rejected |
| Scanner policy | Detection, timeout, error and missing required scanner | Upload is rejected; scanner failure is never displayed as clean |
| DLP and OCR policy | Sensitive patterns and controlled OCR text | Credentials are rejected; findings/unavailable checks can block sharing |
| Share lifecycle | Expiry, revoke, reuse and concurrent redemption | At most one successful redemption |
| Audit integrity | Modified fields and interior deletion | Activity chain reports invalid history |

## Static-analysis notes

Bandit reports seven low-severity findings and no medium/high findings. The subprocess calls invoke local scanner/parser programs using argument lists, never a shell command string, and have explicit timeouts. The XML library warning is for output construction/serialization; untrusted XML is parsed with `defusedxml`. These alerts are retained rather than suppressed.

## Known unverified areas

- OCR accuracy on varied scans, handwriting, low-contrast pages and languages other than English.
- The EICAR ClamAV check, which returned an error instead of a detection result.
- External penetration testing, formal accessibility certification, load testing and multi-instance behavior.
- Commercial Deep CDR, multiple commercial antivirus engines and dynamic sandbox execution; none are included.
- Restoring a real backup into a separate environment; no successful restore is claimed.

## Safe test data

Use only synthetic content from `samples/`. `samples/yara-demo-powershell.txt` is inert text with recognizable strings for a local YARA-X rule. It is not executable malware. Do not upload real credentials, personal records or live malware as a presentation demonstration.
