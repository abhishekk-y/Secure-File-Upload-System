"""Local security policy: bounded reconstruction, DLP and honest static indicators.

No cloud transmission, commercial Deep CDR product or dynamic sandbox is implied.
"""
import collections
import hashlib
import io
import json
import math
import re
import subprocess
import sys
import tempfile
import threading
import os
from pathlib import Path

WORKERS = threading.BoundedSemaphore(2)
MIMES = {
    'txt':'text/plain', 'png':'image/png', 'jpg':'image/jpeg', 'jpeg':'image/jpeg',
    'pdf':'application/pdf', 'docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'csv':'text/csv', 'html':'text/html', 'htm':'text/html', 'xml':'application/xml', 'svg':'image/svg+xml',
}
RECONSTRUCT = {'pdf','docx','csv','html','htm','xml','svg'}
RULE_DIR = Path(os.getenv('YARA_RULES_DIR', Path(__file__).with_name('rules')))


def yara_scan(raw):
    """Compile the maintained local rules and scan bytes; return rule names only."""
    import yara_x
    files = sorted(RULE_DIR.glob('*.yar')) + sorted(RULE_DIR.glob('*.yara'))
    if not files:
        return {'status':'not_configured','matches':[], 'detail':'No local YARA-X rule files were found.'}
    compiler = yara_x.Compiler()
    for rule_file in files:
        if rule_file.stat().st_size > 256 * 1024:
            raise ValueError('A YARA-X rule file exceeds the 256 KiB policy limit.')
        compiler.add_source(rule_file.read_text(encoding='utf-8'), origin=rule_file.name)
    rules = compiler.build()
    scanner = yara_x.Scanner(rules)
    scanner.set_timeout(3)
    results = scanner.scan(raw)
    names = sorted({match.identifier for match in results.matching_rules})
    return {'status':'match' if names else 'no_match', 'matches':names,
            'rule_files':len(files), 'detail':'Local YARA-X signatures only; this is not a malware-free verdict.'}


def ocr_text(raw, mime, root):
    """OCR decoded raster or rendered PDF pages with bounded Tesseract CLI calls."""
    if mime not in ('image/png','image/jpeg','application/pdf'):
        return '', {'status':'not_applicable','characters':0,'detail':'OCR is available for PNG, JPEG and PDF.'}
    executable = os.getenv('TESSERACT_CMD') or ('tesseract.exe' if os.name == 'nt' else 'tesseract')
    try:
        import pypdfium2 as pdfium
        from PIL import Image
        pages=[]
        if mime == 'application/pdf':
            with pdfium.PdfDocument(raw) as document:
                if not 1 <= len(document) <= 10:
                    raise ValueError('PDF page count exceeds the OCR policy.')
                for page in document:
                    width,height=page.get_size()
                    scale=min(1.5,1600/max(width,height))
                    bitmap=page.render(scale=scale,rev_byteorder=True)
                    pages.append(bitmap.to_pil().convert('RGB')); bitmap.close(); page.close()
        else:
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                normalized=image.convert('RGB')
                normalized.thumbnail((2000,2000))
                pages.append(normalized)
        found=[]
        with tempfile.TemporaryDirectory(prefix='ocr-',dir=root) as folder:
            folder=Path(folder)
            for index,page in enumerate(pages):
                source=folder/f'{index}.png'; page.save(source,format='PNG')
                try:
                    result=subprocess.run([executable,str(source), 'stdout','-l',os.getenv('OCR_LANGUAGE','eng'),'--psm','3'],
                                          capture_output=True,timeout=3,check=False)
                except (OSError,subprocess.TimeoutExpired):
                    raise RuntimeError('OCR engine unavailable or timed out') from None
                if result.returncode:
                    raise RuntimeError('OCR engine could not process the document')
                found.append(result.stdout.decode('utf-8',errors='replace'))
                page.close()
        text='\n'.join(found)[:500_000]
        return text, {'status':'text_found' if text.strip() else 'no_text','characters':len(text),
                      'detail':'Tesseract OCR output is transient and used only for DLP; recognition can miss or misread text.'}
    except Exception:
        # Malformed files or parser-specific failures must not turn an optional
        # OCR check into an upload-route error or disclose local paths.
        return '', {'status':'unavailable','characters':0,
                    'detail':'OCR could not process this file; no OCR text was passed to DLP.'}


def reconstruct(raw, extension, root):
    if not WORKERS.acquire(blocking=False):
        raise ValueError('Document processors are busy. Please retry shortly.')
    try:
        with tempfile.TemporaryDirectory(prefix='reconstruct-', dir=root) as folder:
            folder = Path(folder)
            source, output, report = (folder/name for name in ('input','output','report.json'))
            source.write_bytes(raw)
            try:
                result = subprocess.run([sys.executable, str(Path(__file__).with_name('content_worker.py')),
                                         extension, str(source), str(output), str(report)],
                                        capture_output=True, timeout=20)
            except (OSError, subprocess.TimeoutExpired):
                raise ValueError('Document reconstruction timed out or could not start. Upload rejected.') from None
            if result.returncode != 0 or not output.exists() or not report.exists():
                raise ValueError('Document reconstruction failed: malformed, encrypted or over-limit document.')
            if output.stat().st_size > 5*1024*1024 or report.stat().st_size > 4*1024*1024:
                raise ValueError('Reconstruction output exceeds limits.')
            metadata=json.loads(report.read_text(encoding='utf-8'))
            return output.read_bytes(), metadata['text'], metadata['detail']
    finally:
        WORKERS.release()


def luhn(value):
    digits=[int(c) for c in value if c.isdigit()]
    if not 13 <= len(digits) <= 19 or len(set(digits)) < 2:
        return False
    total=0
    for index,digit in enumerate(reversed(digits)):
        if index%2: digit=digit*2-9 if digit>4 else digit*2
        total+=digit
    return total%10==0


def inspect_content(raw, text, connection):
    digest=hashlib.sha256(raw).hexdigest()
    denied=connection.execute('SELECT label FROM blocked_hashes WHERE sha256=?',(digest,)).fetchone()
    if denied:
        raise ValueError('Upload blocked by the local SHA-256 denylist.')
    # The standard antivirus test string is recognized without reproducing it in logs.
    if digest=='275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f':
        raise ValueError('Upload blocked: standard antivirus test signature.')
    if raw.startswith((b'MZ',b'\x7fELF',b'\xfe\xed\xfa\xce',b'\xfe\xed\xfa\xcf')):
        raise ValueError('Executable file signature is not permitted.')
    try:
        yara = yara_scan(raw)
    except Exception as exc:
        raise ValueError('YARA-X inspection failed. Upload rejected for safety.') from exc
    if yara['status'] == 'match':
        raise ValueError('Upload blocked by local YARA-X rule: ' + ', '.join(yara['matches']))
    text=text or ''
    secrets_found=[]
    for label,pattern in [
        ('Private key',r'-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----'),
        ('Access token',r'\b(?:AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9_]{36,}|github_pat_[A-Za-z0-9_]{40,})\b'),
        ('Assigned secret',r'(?i)\b(?:password|api_key|secret_key)\s*[:=]\s*["\x27]?[^\s"\x27]{8,}')]:
        if re.search(pattern,text): secrets_found.append(label)
    if secrets_found:
        raise ValueError('Sensitive-data policy blocked a potential credential. Remove secrets before uploading.')
    findings=[]
    if any(luhn(m.group()) for m in re.finditer(r'\b(?:\d[ -]?){12,18}\d\b',text)):
        findings.append('Possible payment-card number')
    if re.search(r'\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b',text):
        findings.append('Possible personal identifier')
    if len(set(re.findall(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b',text)))>10:
        findings.append('Contact-address list')
    counts=collections.Counter(raw)
    entropy=-sum((count/len(raw))*math.log2(count/len(raw)) for count in counts.values()) if raw else 0
    indicators=[]
    for token,label in [(b'/JavaScript','PDF script marker'),(b'/Launch','PDF launch marker'),(b'<script','Script markup'),(b'vbaProject','Office macro part')]:
        if token.lower() in raw.lower():indicators.append(label)
    return {'policy_version':'3.0','source_sha256':digest,'yara_x':yara,
            'hash_reputation':{'status':'no_match','detail':'No match in local denylist; not a global reputation verdict.'},
            'static_analysis':{'status':'review' if indicators else 'no_match','indicators':indicators,'entropy_bits_per_byte':round(entropy,3),'detail':'Static indicators only; no file execution or dynamic sandbox.'},
            'dlp':{'status':'review' if findings else ('no_match' if text else 'not_applicable'),'findings':findings,'detail':'Pattern checks on extracted and OCR text. OCR can miss or misread content. Matched values are not stored.'},
            'share_allowed':not findings}
