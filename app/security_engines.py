"""
Security Engines Module for SecureVault Phase 2.

This module implements 6 local security engines:
1. DeepCDR: Content Disarm & Reconstruction for PDF, DOCX, SVG, HTML, XML, CSV.
2. ThreatAnalyzer: Pattern matching for executables, scripts, obfuscation.
3. DLPScanner: Regex-based PII/secret detection.
4. VulnerabilityAssessor: Static checks for known attack vectors (XXE, SSRF, etc.).
5. ThreatIntelligence: Local SQLite hash reputation.
6. SandboxAnalyzer: Static behavioral analysis, entropy checking.

An aggregator function `run_all_engines` coordinates the scanning.
"""

import re
import csv
import io
import zipfile
import hashlib
import math
import struct
import collections
import sqlite3
import datetime
import logging
import traceback

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import defusedxml.ElementTree as ET
except ImportError:
    ET = None

try:
    import nh3
except ImportError:
    nh3 = None

logger = logging.getLogger(__name__)

# [Engine 1: DeepCDR]
class DeepCDR:
    """Content Disarm and Reconstruction Engine."""
    def scan(self, raw: bytes, filename: str, mime: str) -> tuple[dict, bytes]:
        status = 'clean'
        details = 'No active content found or removed.'
        sanitized_bytes = raw
        
        try:
            ext = filename.split('.')[-1].lower() if '.' in filename else ''
            
            if ext == 'pdf' or mime == 'application/pdf':
                if pypdf:
                    sanitized_bytes, was_sanitized = self._sanitize_pdf(raw)
                    if was_sanitized:
                        status = 'warning'
                        details = 'Removed active content (JS/Actions) from PDF.'
            elif ext == 'docx' or mime == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                sanitized_bytes, was_sanitized = self._sanitize_docx(raw)
                if was_sanitized:
                    status = 'warning'
                    details = 'Removed macros or active content from DOCX.'
            elif ext == 'svg' or mime == 'image/svg+xml':
                if ET:
                    sanitized_bytes, was_sanitized = self._sanitize_svg(raw)
                    if was_sanitized:
                        status = 'warning'
                        details = 'Sanitized SVG content.'
            elif ext in ('html', 'htm') or mime == 'text/html':
                if nh3:
                    sanitized_bytes, was_sanitized = self._sanitize_html(raw)
                    if was_sanitized:
                        status = 'warning'
                        details = 'Sanitized HTML content.'
            elif ext == 'xml' or mime in ('text/xml', 'application/xml'):
                if ET:
                    sanitized_bytes, was_sanitized = self._sanitize_xml(raw)
                    if was_sanitized:
                        status = 'warning'
                        details = 'Sanitized XML content.'
            elif ext == 'csv' or mime == 'text/csv':
                sanitized_bytes, was_sanitized = self._sanitize_csv(raw)
                if was_sanitized:
                    status = 'warning'
                    details = 'Sanitized CSV content (formula injection protection).'
        except Exception as e:
            logger.error(f"DeepCDR error: {e}")
            return {'engine': 'DeepCDR', 'status': 'warning', 'details': f'CDR failed: {str(e)}'}, raw

        return {'engine': 'DeepCDR', 'status': status, 'details': details}, sanitized_bytes

    def _sanitize_pdf(self, raw: bytes):
        reader = pypdf.PdfReader(io.BytesIO(raw))
        writer = pypdf.PdfWriter()
        was_sanitized = False

        for page in reader.pages:
            if "/AA" in page:
                del page["/AA"]
                was_sanitized = True
            if "/OpenAction" in page:
                del page["/OpenAction"]
                was_sanitized = True
            if "/JS" in page or "/JavaScript" in page:
                if "/JS" in page: del page["/JS"]
                if "/JavaScript" in page: del page["/JavaScript"]
                was_sanitized = True
            writer.add_page(page)

        if reader.metadata:
            if "/Root" in reader.trailer and "/Names" in reader.trailer["/Root"]:
                if "/JavaScript" in reader.trailer["/Root"]["/Names"]:
                    del reader.trailer["/Root"]["/Names"]["/JavaScript"]
                    was_sanitized = True

        out = io.BytesIO()
        writer.write(out)
        return out.getvalue(), was_sanitized

    def _sanitize_docx(self, raw: bytes):
        was_sanitized = False
        in_zip = zipfile.ZipFile(io.BytesIO(raw))
        out_buf = io.BytesIO()
        out_zip = zipfile.ZipFile(out_buf, 'w')
        
        for item in in_zip.infolist():
            if item.filename in ('word/vbaProject.bin', 'word/vbaData.xml') or \
               item.filename.startswith('word/embeddings/') or \
               item.filename.startswith('word/activeX/'):
                was_sanitized = True
                continue
                
            content = in_zip.read(item.filename)
            
            if item.filename.endswith('.rels'):
                if b'TargetMode="External"' in content:
                    was_sanitized = True
                    content = re.sub(b'<Relationship[^>]*TargetMode="External"[^>]*/>', b'', content)
            
            if item.filename == '[Content_Types].xml':
                if b'vbaProject' in content or b'vbaData' in content:
                    was_sanitized = True
                    content = re.sub(b'<Override[^>]*vbaProject[^>]*/>', b'', content)
                    content = re.sub(b'<Override[^>]*vbaData[^>]*/>', b'', content)

            out_zip.writestr(item, content)
            
        out_zip.close()
        return out_buf.getvalue(), was_sanitized

    def _sanitize_svg(self, raw: bytes):
        was_sanitized = False
        try:
            tree = ET.fromstring(raw)
            allowlist = {'svg', 'g', 'path', 'rect', 'circle', 'ellipse', 'line', 'polyline', 
                         'polygon', 'text', 'tspan', 'defs', 'clipPath', 'use', 'image', 'title', 
                         'desc', 'linearGradient', 'radialGradient', 'stop', 'pattern', 'mask', 
                         'filter', 'feGaussianBlur', 'feOffset', 'feMerge', 'feMergeNode', 
                         'symbol', 'marker'}
            
            def clean_node(node):
                nonlocal was_sanitized
                tag = node.tag.split('}')[-1]
                if tag not in allowlist:
                    was_sanitized = True
                    return False
                
                attribs = list(node.attrib.keys())
                for attr in attribs:
                    if attr.startswith('on'):
                        del node.attrib[attr]
                        was_sanitized = True
                    elif attr.endswith('href'):
                        val = node.attrib[attr].lower()
                        if val.startswith('javascript:') or val.startswith('data:text/html'):
                            del node.attrib[attr]
                            was_sanitized = True
                            
                children_to_remove = []
                for child in node:
                    if not clean_node(child):
                        children_to_remove.append(child)
                        
                for child in children_to_remove:
                    node.remove(child)
                    was_sanitized = True
                
                return True

            if not clean_node(tree):
                return b'<svg></svg>', True
                
            import xml.etree.ElementTree as stdET
            return stdET.tostring(tree), was_sanitized
        except ET.ParseError:
            return raw, False

    def _sanitize_html(self, raw: bytes):
        html_str = raw.decode('utf-8', errors='ignore')
        allowlist = {'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'img', 'ul', 'ol', 'li', 'table', 'tr', 'td', 'th', 'thead', 'tbody', 'strong', 'em', 'code', 'pre', 'blockquote', 'span', 'div', 'hr', 'figure', 'figcaption'}
        clean_html = nh3.clean(html_str, tags=allowlist)
        return clean_html.encode('utf-8'), html_str != clean_html

    def _sanitize_xml(self, raw: bytes):
        try:
            tree = ET.fromstring(raw)
            import xml.etree.ElementTree as stdET
            clean_xml = stdET.tostring(tree)
            return clean_xml, clean_xml != raw
        except ET.ParseError:
            return raw, False
            
    def _sanitize_csv(self, raw: bytes):
        was_sanitized = False
        in_str = raw.decode('utf-8', errors='ignore')
        out_buf = io.StringIO()
        reader = csv.reader(io.StringIO(in_str))
        writer = csv.writer(out_buf)
        
        for row in reader:
            new_row = []
            for cell in row:
                if cell.startswith(('=', '+', '-', '@', '\t', '\r')):
                    new_row.append("'" + cell)
                    was_sanitized = True
                else:
                    new_row.append(cell)
            writer.writerow(new_row)
            
        return out_buf.getvalue().encode('utf-8'), was_sanitized


# [Engine 2: ThreatAnalyzer]
class ThreatAnalyzer:
    """Pattern matching for executable signatures, script injection, obfuscation, macro indicators."""
    def scan(self, raw: bytes, filename: str, mime: str) -> dict:
        if raw.startswith(b'MZ') and b'PE\x00\x00' in raw[:512]:
            return {'engine': 'ThreatAnalyzer', 'status': 'blocked', 'details': 'PE Executable detected.'}
        if raw.startswith(b'\x7fELF'):
            return {'engine': 'ThreatAnalyzer', 'status': 'blocked', 'details': 'ELF Executable detected.'}
        if raw[:4] in (b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf', b'\xca\xfe\xba\xbe'):
            if raw.startswith(b'\xca\xfe\xba\xbe'):
                if len(raw) >= 8:
                    version = struct.unpack('>H', raw[6:8])[0]
                    if version >= 45:
                        return {'engine': 'ThreatAnalyzer', 'status': 'blocked', 'details': 'Java Class detected.'}
            return {'engine': 'ThreatAnalyzer', 'status': 'blocked', 'details': 'Mach-O Executable detected.'}
        
        try:
            text = raw.decode('utf-8', errors='ignore').lower()
            if any(p in text for p in ['<script', 'javascript:', 'vbscript:', 'data:text/html']):
                return {'engine': 'ThreatAnalyzer', 'status': 'warning', 'details': 'Script injection patterns detected.'}
                
            macro_keywords = ['autoopen', 'autoexec', 'document_open', 'workbook_open', 'shell', 'createobject', 'wscript', 'powershell', 'cmd.exe']
            if any(k in text for k in macro_keywords):
                return {'engine': 'ThreatAnalyzer', 'status': 'warning', 'details': 'Suspicious macro keywords detected.'}
        except:
            pass
            
        if re.search(b'[A-Za-z0-9+/=]{500,}', raw):
            return {'engine': 'ThreatAnalyzer', 'status': 'warning', 'details': 'Large Base64 block detected.'}
            
        if b'\x90' * 16 in raw:
            return {'engine': 'ThreatAnalyzer', 'status': 'warning', 'details': 'NOP sled detected.'}
            
        return {'engine': 'ThreatAnalyzer', 'status': 'clean', 'details': 'No threat patterns detected.'}


# [Engine 3: DLPScanner]
class DLPScanner:
    """Regex-based PII and secret detection."""
    def _luhn_check(self, num_str: str) -> bool:
        num_str = re.sub(r'\D', '', num_str)
        if not num_str: return False
        s = 0
        is_even = False
        for ch in reversed(num_str):
            d = int(ch)
            if is_even:
                d *= 2
                if d > 9: d -= 9
            s += d
            is_even = not is_even
        return s % 10 == 0

    def _shannon_entropy(self, data: str) -> float:
        if not data: return 0.0
        entropy = 0.0
        for x in set(data):
            p = data.count(x) / len(data)
            entropy += - p * math.log2(p)
        return entropy

    def scan(self, raw: bytes, filename: str, mime: str) -> dict:
        findings = []
        text = raw.decode('utf-8', errors='ignore')
        
        cc_pattern = r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b'
        for match in re.findall(cc_pattern, text):
            if self._luhn_check(match):
                findings.append('Credit Card Number')
                break
                
        ssn_pattern = r'\b(\d{3})-\d{2}-\d{4}\b'
        for match in re.finditer(ssn_pattern, text):
            area = match.group(1)
            if area != '000' and area != '666' and not (900 <= int(area) <= 999):
                findings.append('Social Security Number')
                break
                
        if re.search(r'\bAKIA[0-9A-Z]{16}\b', text): findings.append('AWS Access Key')
        if re.search(r'\bgh[pousr]_[A-Za-z0-9_]{36,}\b', text): findings.append('GitHub Token')
        if re.search(r'\bxox[baprs]-[A-Za-z0-9\-]+\b', text): findings.append('Slack Token')
        if re.search(r'-----BEGIN (RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----', text): findings.append('Private Key')
        
        words = text.split()
        for w in words:
            if len(w) > 20 and self._shannon_entropy(w) > 4.5:
                findings.append('High Entropy String')
                break
                
        emails = re.findall(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
        if len(set(emails)) > 10:
            findings.append('Email Address List (>10)')
            
        if re.search(r'(?i)password\s*[:=]\s*\S+', text):
            findings.append('Password Pattern')
            
        if findings:
            return {'engine': 'DLPScanner', 'status': 'warning', 'details': f"PII/Secrets found: {', '.join(set(findings))}", 'findings': list(set(findings))}
            
        return {'engine': 'DLPScanner', 'status': 'clean', 'details': 'No PII or secrets detected.', 'findings': []}


# [Engine 4: VulnerabilityAssessor]
class VulnerabilityAssessor:
    """Static checks for known attack vectors."""
    def scan(self, raw: bytes, filename: str, mime: str) -> dict:
        text = raw.decode('utf-8', errors='ignore')
        text_lower = text.lower()
        
        if '<!doctype' in text_lower and 'entity' in text_lower and 'system' in text_lower:
            return {'engine': 'VulnerabilityAssessor', 'status': 'blocked', 'details': 'XXE vector detected.'}
            
        if 'dde' in text_lower or 'ddeauto' in text_lower:
            return {'engine': 'VulnerabilityAssessor', 'status': 'blocked', 'details': 'DDE injection detected.'}
            
        ssrf_patterns = [r'127\.0\.0\.1', r'169\.254\.\d+\.\d+', r'10\.\d+\.\d+\.\d+', r'172\.(?:1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+', r'192\.168\.\d+\.\d+', r'file://', r'\\\\', r'localhost']
        if any(re.search(p, text_lower) for p in ssrf_patterns):
            return {'engine': 'VulnerabilityAssessor', 'status': 'warning', 'details': 'SSRF vector detected.'}
            
        if '../' in text or '..\\' in text:
            return {'engine': 'VulnerabilityAssessor', 'status': 'warning', 'details': 'Path traversal sequence detected.'}
            
        if filename.lower().endswith('.csv') or mime == 'text/csv':
            if any(re.search(r'^[=+\-@].*(cmd|hyperlink|importdata)', line, re.I) for line in text.splitlines()):
                return {'engine': 'VulnerabilityAssessor', 'status': 'warning', 'details': 'Dangerous formula injection detected.'}
                
        magic_bytes = {
            b'%PDF': 'pdf',
            b'\x89PNG': 'png',
            b'MZ': 'pe',
            b'PK\x03\x04': 'zip'
        }
        
        matched_magic = None
        for magic, name in magic_bytes.items():
            if raw.startswith(magic):
                matched_magic = name
                break
                
        if matched_magic:
            for magic, name in magic_bytes.items():
                if name != matched_magic and magic in raw[len(matched_magic):1024]:
                    return {'engine': 'VulnerabilityAssessor', 'status': 'warning', 'details': f'Polyglot file detected ({matched_magic} + {name}).'}
        
        return {'engine': 'VulnerabilityAssessor', 'status': 'clean', 'details': 'No static vulnerabilities detected.'}


# [Engine 5: ThreatIntelligence]
class ThreatIntelligence:
    """Local-only hash reputation DB."""
    def scan(self, raw: bytes, filename: str, mime: str, db_path: str = None) -> dict:
        if not db_path:
            return {'engine': 'ThreatIntelligence', 'status': 'clean', 'details': 'No DB path provided.'}
            
        sha256 = hashlib.sha256(raw).hexdigest()
        
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            
            c.execute('''CREATE TABLE IF NOT EXISTS threat_hashes (sha256 TEXT PRIMARY KEY, threat_name TEXT, severity TEXT, added_at TEXT)''')
            c.execute('''CREATE TABLE IF NOT EXISTS hash_sightings (sha256 TEXT, user_id TEXT, seen_at TEXT)''')
            
            eicar = "275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f"
            c.execute("INSERT OR IGNORE INTO threat_hashes VALUES (?, ?, ?, ?)", (eicar, "EICAR Test File", "high", datetime.datetime.now().isoformat()))
            conn.commit()
            
            c.execute("SELECT threat_name FROM threat_hashes WHERE sha256 = ?", (sha256,))
            row = c.fetchone()
            if row:
                conn.close()
                return {'engine': 'ThreatIntelligence', 'status': 'blocked', 'details': f'Known threat hash: {row[0]}'}
                
            c.execute("INSERT INTO hash_sightings VALUES (?, ?, ?)", (sha256, 'anonymous', datetime.datetime.now().isoformat()))
            conn.commit()
            
            c.execute("SELECT COUNT(DISTINCT user_id) FROM hash_sightings WHERE sha256 = ?", (sha256,))
            count = c.fetchone()[0]
            conn.close()
            
            if count > 3:
                return {'engine': 'ThreatIntelligence', 'status': 'warning', 'details': 'Suspicious upload frequency for this hash.'}
                
        except Exception as e:
            logger.error(f"ThreatIntelligence DB error: {e}")
            return {'engine': 'ThreatIntelligence', 'status': 'clean', 'details': f'Error querying DB: {str(e)}'}
            
        return {'engine': 'ThreatIntelligence', 'status': 'clean', 'details': 'Hash is clean.'}


# [Engine 6: SandboxAnalyzer]
class SandboxAnalyzer:
    """Static behavioral analysis and entropy analysis."""
    def _calculate_entropy(self, data: bytes) -> float:
        if not data: return 0.0
        entropy = 0.0
        for x in range(256):
            p = data.count(bytes([x])) / len(data)
            if p > 0:
                entropy += - p * math.log2(p)
        return entropy

    def scan(self, raw: bytes, filename: str, mime: str) -> dict:
        text = raw.decode('utf-8', errors='ignore')
        
        if b'/OpenAction' in raw or b'/AA' in raw or b'/Launch' in raw or b'/JS' in raw or b'/JavaScript' in raw:
            if filename.lower().endswith('.pdf') or mime == 'application/pdf':
                return {'engine': 'SandboxAnalyzer', 'status': 'warning', 'details': 'PDF auto-exec or JS detected.'}
                
        if any(kw in text.lower() for kw in ['autoopen', 'document_open', 'auto_open']):
            if filename.lower().endswith('.docx') or mime == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                return {'engine': 'SandboxAnalyzer', 'status': 'warning', 'details': 'DOCX auto-exec macros detected.'}
                
        overall_entropy = self._calculate_entropy(raw)
        if overall_entropy > 7.0:
            return {'engine': 'SandboxAnalyzer', 'status': 'warning', 'details': 'High file entropy (>7.0), possibly packed/encrypted.'}
            
        block_size = 1024
        for i in range(0, len(raw), block_size):
            block = raw[i:i+block_size]
            if len(block) == block_size and self._calculate_entropy(block) > 7.5:
                return {'engine': 'SandboxAnalyzer', 'status': 'warning', 'details': 'High block entropy (>7.5) detected.'}
                
        if b'MZ' in raw[2:] and b'PE\x00\x00' in raw:
            return {'engine': 'SandboxAnalyzer', 'status': 'warning', 'details': 'Embedded PE executable detected.'}
        if b'\x7fELF' in raw[4:]:
            return {'engine': 'SandboxAnalyzer', 'status': 'warning', 'details': 'Embedded ELF executable detected.'}
            
        urls = re.findall(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', text)
        if len(urls) > 10:
             return {'engine': 'SandboxAnalyzer', 'status': 'warning', 'details': f'Many URLs extracted ({len(urls)}).'}
             
        ek_names = ['angler', 'rig', 'magnitude', 'sundown', 'fallout']
        if any(ek in text.lower() for ek in ek_names):
             return {'engine': 'SandboxAnalyzer', 'status': 'warning', 'details': 'Exploit kit metadata strings detected.'}
             
        return {'engine': 'SandboxAnalyzer', 'status': 'clean', 'details': 'Behavioral analysis clean.'}


def run_all_engines(raw: bytes, filename: str, mime: str, db_path: str = None) -> dict:
    """
    Runs all 6 engines on the provided file content and returns an aggregated report.
    """
    report = {
        'blocked': False,
        'block_reason': None,
        'warnings': [],
        'engines': {},
        'sanitized_bytes': None,
        'summary': ''
    }
    
    # 1. DeepCDR
    try:
        cdr = DeepCDR()
        cdr_res, san_bytes = cdr.scan(raw, filename, mime)
        report['engines']['deep_cdr'] = cdr_res
        if cdr_res['status'] != 'clean':
            report['sanitized_bytes'] = san_bytes
    except Exception as e:
        report['engines']['deep_cdr'] = {'engine': 'DeepCDR', 'status': 'error', 'details': str(e)}
        
    # 2. ThreatAnalyzer
    try:
        ta = ThreatAnalyzer()
        ta_res = ta.scan(raw, filename, mime)
        report['engines']['threat_analyzer'] = ta_res
    except Exception as e:
        report['engines']['threat_analyzer'] = {'engine': 'ThreatAnalyzer', 'status': 'error', 'details': str(e)}

    # 3. DLPScanner
    try:
        dlp = DLPScanner()
        dlp_res = dlp.scan(raw, filename, mime)
        report['engines']['dlp'] = dlp_res
    except Exception as e:
        report['engines']['dlp'] = {'engine': 'DLPScanner', 'status': 'error', 'details': str(e)}
        
    # 4. VulnerabilityAssessor
    try:
        va = VulnerabilityAssessor()
        va_res = va.scan(raw, filename, mime)
        report['engines']['vulnerability'] = va_res
    except Exception as e:
        report['engines']['vulnerability'] = {'engine': 'VulnerabilityAssessor', 'status': 'error', 'details': str(e)}

    # 5. ThreatIntelligence
    try:
        ti = ThreatIntelligence()
        ti_res = ti.scan(raw, filename, mime, db_path=db_path)
        report['engines']['threat_intel'] = ti_res
    except Exception as e:
        report['engines']['threat_intel'] = {'engine': 'ThreatIntelligence', 'status': 'error', 'details': str(e)}

    # 6. SandboxAnalyzer
    try:
        sa = SandboxAnalyzer()
        sa_res = sa.scan(raw, filename, mime)
        report['engines']['sandbox'] = sa_res
    except Exception as e:
        report['engines']['sandbox'] = {'engine': 'SandboxAnalyzer', 'status': 'error', 'details': str(e)}

    for eng_name, res in report['engines'].items():
        if res['status'] == 'blocked':
            report['blocked'] = True
            if not report['block_reason']:
                report['block_reason'] = res['details']
        elif res['status'] == 'warning':
            report['warnings'].append(f"{res['engine']}: {res['details']}")
            
    if report['blocked']:
        report['summary'] = f"File blocked: {report['block_reason']}"
    elif report['warnings']:
        report['summary'] = f"File passed with warnings: {len(report['warnings'])} warnings found."
    else:
        report['summary'] = "File is clean."
        
    return report
