"""Bounded format reconstruction in a short-lived worker process.

This is process separation with a timeout, not an OS security sandbox.
Only reconstructed output is retained; input files are never executed.
"""
import csv
import io
import json
import math
import sys
import zipfile
from pathlib import Path, PurePosixPath
import xml.etree.ElementTree as StdET  # Output construction only; untrusted XML uses SafeET.
from defusedxml import ElementTree as SafeET

MAX_BYTES = 50 * 1024 * 1024
MAX_TEXT = 500_000


def text_input(raw):
    text = raw.decode('utf-8-sig')
    if any(ord(c) < 32 and c not in '\t\r\n' for c in text):
        raise ValueError('Binary control characters are not allowed in text documents.')
    return text


def rebuild(raw, ext):
    extracted = ''
    if ext == 'pdf':
        import pypdfium2 as pdfium
        from PIL import Image
        if not raw.startswith(b'%PDF-'):
            raise ValueError('PDF signature mismatch.')
        images = []
        with pdfium.PdfDocument(raw) as document:
            if not 1 <= len(document) <= 10:
                raise ValueError('PDF must contain 1 to 10 pages.')
            for page in document:
                width, height = page.get_size()
                if not all(math.isfinite(v) and 1 <= v <= 14400 for v in (width, height)):
                    raise ValueError('PDF page dimensions are outside the allowed range.')
                scale = min(1.5, 1600 / max(width, height))
                textpage = page.get_textpage()
                try:
                    count = textpage.count_chars()
                    if count > MAX_TEXT or len(extracted) + count > MAX_TEXT:
                        raise ValueError('PDF text exceeds processing limit.')
                    extracted += textpage.get_text_range() + '\n'
                finally:
                    textpage.close()
                bitmap = page.render(scale=scale, rev_byteorder=True)
                images.append(bitmap.to_pil().convert('RGB'))
                bitmap.close()
                page.close()
        output = io.BytesIO()
        images[0].save(output, format='PDF', save_all=True, append_images=images[1:], resolution=108, quality=85)
        result = output.getvalue()
        detail = 'PDF reconstructed from rendered pages; scripts, links, attachments, forms and original metadata are not copied. Searchable text and signatures are lost.'
        for image in images:
            image.close()
    elif ext == 'docx':
        if not raw.startswith(b'PK\x03\x04'):
            raise ValueError('DOCX must be an OOXML ZIP container.')
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            names = [item.filename for item in entries]
            if len(entries) > 200 or len(set(names)) != len(names):
                raise ValueError('DOCX has too many or duplicate ZIP entries.')
            if sum(item.file_size for item in entries) > 20 * 1024 * 1024:
                raise ValueError('DOCX expanded size exceeds 20 MiB.')
            for item in entries:
                path = PurePosixPath(item.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in item.filename or item.flag_bits & 1:
                    raise ValueError('DOCX contains an unsafe or encrypted ZIP entry.')
                if item.file_size > 100 * max(item.compress_size, 1):
                    raise ValueError('DOCX compression ratio exceeds policy.')
            if not {'[Content_Types].xml', 'word/document.xml', '_rels/.rels'}.issubset(names):
                raise ValueError('Required DOCX parts are missing.')
            SafeET.fromstring(archive.read('[Content_Types].xml'), forbid_dtd=True)
            root = SafeET.fromstring(archive.read('word/document.xml'), forbid_dtd=True)
        ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
        if root.tag != '{'+ns+'}document':
            raise ValueError('Invalid DOCX document root.')
        paragraphs = [''.join(p.itertext()) for p in root.findall('.//{'+ns+'}p')]
        # Only text runs are retained, never field instructions, relationships or embedded objects.
        paragraphs = [''.join(n.text or '' for n in p.iter('{'+ns+'}t')) for p in root.findall('.//{'+ns+'}p')]
        extracted = '\n'.join(paragraphs)
        if len(extracted) > MAX_TEXT:
            raise ValueError('DOCX text exceeds processing limit.')
        newroot = StdET.Element('{'+ns+'}document')
        body = StdET.SubElement(newroot, '{'+ns+'}body')
        for line in paragraphs:
            p = StdET.SubElement(body, '{'+ns+'}p')
            run = StdET.SubElement(p, '{'+ns+'}r')
            node = StdET.SubElement(run, '{'+ns+'}t')
            node.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            node.text = line
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as rebuilt:
            rebuilt.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
            rebuilt.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
            rebuilt.writestr('word/document.xml', StdET.tostring(newroot, encoding='utf-8', xml_declaration=True))
        result = output.getvalue()
        detail = 'DOCX rebuilt as plain paragraphs; macros, embedded objects, external relationships, images, fields and formatting are discarded.'
    elif ext == 'csv':
        source = text_input(raw)
        extracted = source
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        changed = 0
        for index, row in enumerate(csv.reader(io.StringIO(source), strict=True)):
            if index >= 10000 or len(row) > 100:
                raise ValueError('CSV exceeds 10,000 rows or 100 columns.')
            clean = []
            for cell in row:
                if cell.lstrip().startswith(('=', '+', '-', '@')) or cell.startswith(('\t', '\r')):
                    cell = "'" + cell
                    changed += 1
                clean.append(cell)
            writer.writerow(clean)
        result = output.getvalue().encode('utf-8')
        detail = f'CSV reconstructed; {changed} formula-like cells prefixed with an apostrophe. Spreadsheet import settings still matter.'
    elif ext in ('html', 'htm'):
        import nh3
        source = text_input(raw)
        safe = nh3.clean(source, tags={'p','br','h1','h2','h3','h4','h5','h6','ul','ol','li','table','tr','td','th','thead','tbody','strong','em','code','pre','blockquote','span','div','hr'}, attributes={}, clean_content_tags={'script','style','iframe','object','template'}, link_rel=None)
        extracted = nh3.clean(source, tags=set(), attributes={}, link_rel=None)
        result = ('<!doctype html><html><head><meta charset="utf-8"><title>Sanitized document</title></head><body>'+safe+'</body></html>').encode('utf-8')
        detail = 'HTML rebuilt with basic formatting only; scripts, links, images, style and attributes removed. Download only.'
    elif ext in ('xml', 'svg'):
        source = text_input(raw)
        root = SafeET.fromstring(source, forbid_dtd=True)
        nodes = list(root.iter())
        if len(nodes) > 10000:
            raise ValueError('XML node limit exceeded.')
        extracted = ' '.join(node.text or '' for node in nodes)
        if ext == 'svg':
            ns = 'http://www.w3.org/2000/svg'
            if root.tag not in ('svg', '{'+ns+'}svg'):
                raise ValueError('SVG root element is missing.')
            tags={'svg','g','path','rect','circle','ellipse','line','polyline','polygon','text','tspan','title','desc'}
            attrs={'x','y','x1','y1','x2','y2','cx','cy','r','rx','ry','width','height','viewBox','d','points','fill','stroke','stroke-width','transform','font-size'}
            for node in nodes:
                for child in list(node):
                    if child.tag.split('}')[-1] not in tags:
                        node.remove(child)
                for name,value in list(node.attrib.items()):
                    if name not in attrs or any(token in value.lower() for token in ('url(', 'http:', 'https:', 'data:', 'javascript:', '@', '&')):
                        del node.attrib[name]
            detail = 'SVG restricted to basic shapes and text; scripts, styles, links, external resources and filters discarded. Download only.'
        else:
            # Remove attributes and namespace elements with execution/expansion semantics.
            for node in nodes:
                node.attrib.clear()
                for child in list(node):
                    if child.tag.startswith('{http://www.w3.org/2001/XInclude}'):
                        node.remove(child)
            detail = 'XML parsed without DTD/entities; attributes, processing instructions and XInclude removed. Data structure may change. Download only.'
        result = StdET.tostring(root, encoding='utf-8', xml_declaration=True)
    else:
        raise ValueError('Unsupported reconstruction format.')
    if not result or len(result) > MAX_BYTES or len(extracted) > MAX_TEXT:
        raise ValueError('Reconstructed output or extracted text exceeds limits.')
    return result, extracted, detail


if __name__ == '__main__':
    ext, source, destination, report = sys.argv[1:]
    try:
        if sys.platform != 'win32':
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (768*1024*1024, 768*1024*1024))
            resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
        raw = Path(source).read_bytes()
        if len(raw) > MAX_BYTES:
            raise ValueError('Input exceeds 50 MiB.')
        output, text, detail = rebuild(raw, ext)
        Path(destination).write_bytes(output)
        Path(report).write_text(json.dumps({'text':text,'detail':detail}), encoding='utf-8')
    except Exception as error:
        # Parser errors must never release the original input as a successful result.
        Path(report).write_text(json.dumps({'error': str(error)[:200]}), encoding='utf-8')
        sys.exit(1)
