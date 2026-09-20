import io

import pytest
from PIL import Image, ImageDraw

from app.document_scanner import scan_document
from test_security import account, app, post, rows


def document_photo():
    image = Image.new('RGB', (800, 700), '#303030')
    draw = ImageDraw.Draw(image)
    draw.polygon([(130, 70), (650, 120), (700, 620), (90, 580)], fill='white')
    for y in range(180, 500, 45):
        draw.line((180, y, 570, y+12), fill='black', width=5)
    stream = io.BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


def test_document_page_is_rectified():
    result, status = scan_document(document_photo(), 'image/png')
    assert 'straightened' in status
    with Image.open(io.BytesIO(result)) as image:
        assert image.mode == 'L'
        assert 400 < image.width < 700
        assert 400 < image.height < 650
        assert not image.getexif()


def test_no_boundary_retains_frame():
    stream = io.BytesIO()
    Image.new('RGB', (100, 140), 'gray').save(stream, 'PNG')
    result, status = scan_document(stream.getvalue(), 'image/png')
    assert 'without cropping' in status
    assert Image.open(io.BytesIO(result)).size == (100, 140)


def test_text_cannot_be_document_scanned():
    with pytest.raises(ValueError, match='PNG or JPEG'):
        scan_document(b'hello', 'text/plain')


def test_scanned_upload_remains_encrypted_and_downloadable(app):
    owner = account(app)
    response = post(owner, '/upload', {'file': (io.BytesIO(document_photo()), 'page.png'), 'document_scan': '1'})
    assert response.status_code == 200
    assert b'Page detected, straightened and enhanced.' in response.data
    file = rows(app)[0]
    downloaded = owner.get(f"/files/{file['id']}/download")
    assert downloaded.status_code == 200
    assert Image.open(io.BytesIO(downloaded.data)).mode == 'L'
    assert 'straightened' in file['processing']
    assert any(row['action'] == 'Document processed' for row in rows(app, 'events'))


def test_scan_option_rejects_text_without_creating_file(app):
    owner = account(app)
    post(owner, '/upload', {'file': (io.BytesIO(b'notes'), 'notes.txt'), 'document_scan': '1'})
    assert not rows(app)


def test_inspection_report_is_private_and_truthful(app):
    from test_security import upload
    owner = account(app)
    upload(owner)
    identity = rows(app)[0]['id']
    response = owner.get(f'/files/{identity}/inspection')
    assert response.status_code == 200
    report = response.json
    assert report['antivirus'] == 'Not scanned'
    assert report['document_processing'] == 'Not requested'
    assert 'verified at report generation' in report['integrity']
    stranger = account(app, 'bob')
    assert stranger.get(f'/files/{identity}/inspection').status_code == 404


def test_inspection_rejects_corrupt_blob(app):
    from pathlib import Path
    from test_security import upload
    owner = account(app)
    upload(owner)
    identity = rows(app)[0]['id']
    (Path(app.config['DATA_DIR']) / 'vault' / identity).write_bytes(b'corrupt')
    assert owner.get(f'/files/{identity}/inspection').status_code == 409
