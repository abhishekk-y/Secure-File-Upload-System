import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from app.content_worker import rebuild
from app.security_engines import inspect_content, reconstruct, yara_scan, ocr_text
from test_security import account, app, post, rows


def docx_fixture():
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:
        archive.writestr('[Content_Types].xml','<Types/>')
        archive.writestr('_rels/.rels','<Relationships/>')
        archive.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Project notes</w:t></w:r></w:p></w:body></w:document>')
        archive.writestr('word/vbaProject.bin',b'discard this fixture')
        archive.writestr('word/embeddings/attachment.bin',b'not retained')
    return out.getvalue()


def test_docx_is_rebuilt_not_copied():
    result,text,detail=rebuild(docx_fixture(),'docx')
    with zipfile.ZipFile(io.BytesIO(result)) as archive:
        assert set(archive.namelist())=={'[Content_Types].xml','_rels/.rels','word/document.xml'}
    assert text=='Project notes'
    assert 'discarded' in detail


def test_pdf_is_image_only():
    source=io.BytesIO()
    Image.new('RGB',(300,200),'white').save(source,'PDF')
    result,_,detail=rebuild(source.getvalue(),'pdf')
    assert result.startswith(b'%PDF-')
    assert 'rendered pages' in detail
    import pypdfium2 as pdfium
    with pdfium.PdfDocument(result) as document:
        assert len(document)==1
        assert document[0].get_textpage().count_chars()==0


@pytest.mark.parametrize('ext,source,forbidden',[
    ('html',b'<p onclick="alert(1)">Hello</p><script>alert(1)</script><img src="https://example.invalid/a">',[b'onclick',b'<script',b'example.invalid']),
    ('svg',b'<svg xmlns="http://www.w3.org/2000/svg"><script>bad</script><image href="https://example.invalid"/><rect width="10" onload="bad" fill="url(http://example.invalid)"/></svg>',[b'<script',b'onload',b'href',b'url(']),
    ('xml',b'<?xml version="1.0"?><root secret="discard"><value>Safe</value></root>',[b'secret=']),
])
def test_markup_active_content_removed(ext,source,forbidden):
    result,_,_=rebuild(source,ext)
    assert all(token not in result for token in forbidden)


def test_csv_formula_neutralization():
    result,_,_=rebuild(b'name,value\nexample,=1+1\nspace,  @SUM(A1)\n','csv')
    assert b"'=1+1" in result
    assert b"'  @SUM" in result


@pytest.mark.parametrize('ext,raw',[
    ('xml',b'<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>'),
    ('svg',b'<html>not SVG</html>'),('pdf',b'%PDF-malformed'),('docx',b'PK\x03\x04broken'),
])
def test_malformed_and_entity_documents_rejected(tmp_path,ext,raw):
    with pytest.raises(ValueError,match='reconstruction failed'):
        reconstruct(raw,ext,tmp_path)


def test_docx_zip_bomb_rejected():
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('large.xml',b'A'*1_000_000)
    with pytest.raises(ValueError,match='compression ratio'):
        rebuild(out.getvalue(),'docx')


def test_dlp_never_records_matched_values():
    connection=sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE blocked_hashes(sha256 TEXT,label TEXT)')
    text='Payment test: 4111 1111 1111 1111'
    report=inspect_content(text.encode(),text,connection)
    assert not report['share_allowed']
    assert '4111' not in json.dumps(report)
    with pytest.raises(ValueError,match='credential'):
        inspect_content(b'notes','-----BEGIN PRIVATE KEY-----',connection)


def test_hash_denylist_blocks():
    connection=sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE blocked_hashes(sha256 TEXT,label TEXT)')
    connection.execute('INSERT INTO blocked_hashes VALUES(?,?)',(hashlib.sha256(b'blocked fixture').hexdigest(),'fixture'))
    with pytest.raises(ValueError,match='denylist'):
        inspect_content(b'blocked fixture','',connection)


@pytest.mark.parametrize(('sample','expected'), [
    (b'ordinary project notes', 'no_match'),
    (b'SECUREVAULT-DEMO-SIGNATURE-MATCH', 'SecureVault_Training_Marker'),
    (b'powershell -EncodedCommand abc; [Convert]::FromBase64String(abc)', 'PowerShell_Encoded_Command'),
    (b'const x=atob(data); eval(x);', 'JavaScript_Dynamic_Decode_And_Execution'),
    (b'AutoOpen() { Shell("tool") }', 'Office_AutoOpen_And_Shell_Execution'),
    (b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*', 'EICAR_Antivirus_Test_File'),
])
def test_local_yara_x_rules_match_explainable_fixtures(sample, expected):
    result = yara_scan(sample)
    if expected == 'no_match':
        assert result['status'] == 'no_match'
    else:
        assert expected in result['matches']


def test_ocr_skips_unsupported_content(tmp_path):
    text, result = ocr_text(b'notes', 'text/plain', tmp_path)
    assert text == ''
    assert result['status'] == 'not_applicable'


def test_ocr_parser_failure_is_reported_without_leaking_details(tmp_path,monkeypatch):
    import sys
    from types import SimpleNamespace
    class BrokenPDF:
        def __init__(self, raw):
            raise OSError('parser failure at C:\\private\\upload.pdf')
    monkeypatch.setitem(sys.modules,'pypdfium2',SimpleNamespace(PdfDocument=BrokenPDF))
    text,result=ocr_text(b'malformed','application/pdf',tmp_path)
    assert text==''
    assert result['status']=='unavailable'
    assert 'private' not in result['detail']


def test_safe_yara_demo_download_requires_login_and_uses_inert_fixture(app):
    guest=app.test_client()
    assert guest.get('/demo/yara-sample').status_code==302
    owner=account(app)
    response=owner.get('/demo/yara-sample')
    fixture=(Path(__file__).resolve().parents[1]/'samples'/'yara-demo-powershell.txt').read_bytes()
    assert response.status_code==200
    assert response.mimetype=='text/plain'
    assert b'attachment' in response.headers['Content-Disposition'].encode().lower()
    assert response.data==fixture


def test_advanced_upload_report_and_dlp_share_gate(app):
    owner=account(app)
    response=post(owner,'/upload',{'file':(io.BytesIO(b'<p>Hello</p><script>bad</script>'),'notes.html','text/html')})
    assert b'encrypted and saved' in response.data
    row=rows(app)[0]
    assert b'<script' not in owner.get(f"/files/{row['id']}/download").data
    assert owner.get(f"/files/{row['id']}/preview").status_code==404
    assert owner.get(f"/files/{row['id']}/report").status_code==200
    inspection=json.loads(owner.get(f"/files/{row['id']}/inspection").data)
    assert inspection['security_checks']['yara_x']['status']=='no_match'
    assert inspection['security_checks']['ocr']['status']=='not_applicable'
    vault=owner.get('/vault').get_data(as_text=True)
    assert 'YARA-X no match · DLP no match' in vault
    assert 'OCR not applicable' in vault
    assert '<dt>YARA-X</dt><dd>no match</dd>' in vault
    assert '<dt>DLP</dt><dd>no match</dd>' in vault
    post(owner,'/upload',{'file':(io.BytesIO(b'Payment test: 4111 1111 1111 1111'),'payment.txt')})
    row=rows(app)[1]
    assert not json.loads(row['security_report'])['share_allowed']
    response=post(owner,f"/files/{row['id']}/share")
    assert b'Sharing is blocked' in response.data
    assert not rows(app,'shares')


def test_ocr_failure_keeps_visual_file_private_and_disables_share(app, monkeypatch):
    import app as vault_app
    owner=account(app)
    image=io.BytesIO()
    Image.new('RGB',(100,100),'white').save(image,format='PNG')
    monkeypatch.setattr(vault_app,'ocr_text',lambda *_:('',{
        'status':'unavailable','characters':0,'detail':'OCR unavailable in test'}))
    response=post(owner,'/upload',{'file':(io.BytesIO(image.getvalue()),'scan.png','image/png')})
    assert b'encrypted and saved' in response.data
    row=rows(app)[0]
    report=json.loads(row['security_report'])
    assert report['ocr']['status']=='unavailable'
    assert report['share_allowed'] is False
    assert b'Sharing is disabled' in owner.get('/vault').data
    assert b'Sharing is blocked' in post(owner,f"/files/{row['id']}/share").data
    assert not rows(app,'shares')


def test_yara_match_rejects_upload_before_storage(app):
    owner=account(app)
    suspicious=b'powershell -EncodedCommand AAAA [Convert]::FromBase64String(AAAA)'
    response=post(owner,'/upload',{'file':(io.BytesIO(suspicious),'yara-demo.txt','text/plain')})
    assert b'YARA-X rule' in response.data
    assert rows(app)==[]


def test_worker_timeout_is_rejection(tmp_path,monkeypatch):
    import subprocess
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('worker',20)
    monkeypatch.setattr(subprocess,'run',timeout)
    with pytest.raises(ValueError,match='timed out'):
        reconstruct(b'a,b','csv',tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(('sample','expected'),[
    (b'ordinary project notes',None),
    (b'SECUREVAULT-DEMO-SIGNATURE-MATCH','SecureVault_Training_Marker'),
    (b'powershell -EncodedCommand abc; [Convert]::FromBase64String(abc)','PowerShell_Encoded_Command'),
    (b'const x=atob(data); eval(x);','JavaScript_Dynamic_Decode_And_Execution'),
    (b'AutoOpen() { Shell("tool") }','Office_AutoOpen_And_Shell_Execution'),
    (b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*','EICAR_Antivirus_Test_File'),
])
def test_yara_x_local_rules(sample,expected):
    result=yara_scan(sample)
    assert result['status']==('no_match' if expected is None else 'match')
    if expected:
        assert expected in result['matches']


def test_ocr_skips_unsupported_file_type(tmp_path):
    text,result=ocr_text(b'plain text','text/plain',tmp_path)
    assert text=='' and result['status']=='not_applicable'


def test_ocr_output_is_sent_to_dlp_without_recording_value(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import app.security_engines as engines
    image=io.BytesIO()
    Image.new('RGB',(120,60),'white').save(image,format='PNG')
    monkeypatch.setattr(engines.subprocess,'run',lambda *args,**kwargs: SimpleNamespace(returncode=0,stdout=b'password: correct-horse-battery'))
    text,result=ocr_text(image.getvalue(),'image/png',tmp_path)
    assert result['status']=='text_found'
    assert 'correct-horse-battery' in text
    connection=sqlite3.connect(':memory:')
    connection.execute('CREATE TABLE blocked_hashes(sha256 TEXT,label TEXT)')
    with pytest.raises(ValueError,match='credential'):
        inspect_content(image.getvalue(),text,connection)
