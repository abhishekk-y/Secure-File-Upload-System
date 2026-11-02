# Safe demonstration files

These files contain synthetic content for a classroom demonstration. Do not replace them with real personal, payment or credential data.

- `demo-notes.txt` is ordinary content for a clean path.
- `yara-demo-powershell.txt` is inert text containing string combinations that the local YARA-X PowerShell rule recognizes. The upload should be rejected with the rule name. Do not execute it.
- `document-photo.png` is a sample image for optional OpenCV page correction.
- `ocr-demo.png` is a generated page with the synthetic phrase `password: demo-password-123`. With Tesseract installed, OCR should extract the phrase and DLP should reject upload without storing the matched value. Without Tesseract, the report should say OCR unavailable; do not describe that as an OCR pass.

Tesseract output depends on image quality, language data and installation. These fixtures demonstrate the flow; they do not measure recognition accuracy.
