# Presentation speaker notes

## Slide 1 SecureVault
Introduce SecureVault as an academic Secure File Upload System. Replace the student/institution fields on this slide. The presentation distinguishes verified local controls from enterprise services requiring licenses.

## Slide 2 An upload is a trust decision.
Describe the three risks, then show the actual earlier workspace screenshot. The final source additionally supports document formats and inspection reports; the screenshot is not an exhaustive feature list.

## Slide 3 Research to implementation
The corpus is purposive: one paper each in 2020, 2022 and 2024. No citation-count or global trend claim is made. Full records and URLs are in the report and literature-corpus.csv.

## Slide 4 System architecture
Browser bytes are untrusted. The server holds encryption keys. Reconstruction runs in separate bounded processes; this is not a hardened malware sandbox or dynamic execution environment.

## Slide 5 From upload to one-use delivery
Explain each gate in order. ClamAV scans the original and changed output. DLP can allow private storage but deny sharing. The code is consumed atomically before network delivery completes.

## Slide 6 Technology you can locate in the code
Use the file tree to answer where a feature is implemented. The detailed report will expand the schema, SRS and algorithms in the next writing phase. All security decisions are enforced server-side.

## Slide 7 Advanced features, honest outcomes
Reconstruction is deliberately lossy. OpenCV cleans page images. YARA-X gives local rule matches; Tesseract OCR adds text for DLP. Neither guarantees detection.

## Slide 8 Access is a relationship, not a filename.
Each file belongs to an owner. Sessions contain hashed tokens. Shares contain hashed capabilities, expiry and use state. HMAC audit chains detect edits/interior deletion but not suffix truncation without an external checkpoint.

## Slide 9 Why this design is distinctive
Compare alternatives without claiming a benchmark. The design favors local inspectability. High throughput, key management and hardened isolation require additional infrastructure.

## Slide 10 SDLC and future scope
There is no invented six-week schedule. Current functionality and future service integrations are explicitly separated.

## Slide 11 Demonstrate. Explain. Defend.
Full references: `docs/RESEARCH.md` and the reference list in `README.md`. Replace student fields before presenting.

## Slide 12 A visual tour of SecureVault
Use these interface captures to orient the audience before the live workflow. Demonstrate current YARA-X and OCR status in the owner inspection report because the reported state depends on local scanner configuration.
