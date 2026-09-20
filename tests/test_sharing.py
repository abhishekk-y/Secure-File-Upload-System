import hashlib
import io
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image
from test_security import account, app, post, rows, token, upload


def share(client, identity):
    result = post(client, f'/files/{identity}/share')
    code = re.search(r'id="share-code">([A-F0-9-]+)', result.get_data(as_text=True)).group(1)
    return code


def redeem(client, code):
    return post(client, '/receive', {'code': code}, '/receive')


def test_landing_and_all_workspace_pages(app):
    assert app.test_client().get('/').status_code == 200
    client = account(app)
    for path in ['/vault', '/activity', '/security', '/shares', '/receive']:
        assert client.get(path).status_code == 200


def test_share_once_and_hash_only(app):
    owner = account(app)
    upload(owner)
    code = share(owner, rows(app)[0]['id'])
    stored = rows(app, 'shares')[0]
    assert stored['token_hash'] == hashlib.sha256(code.replace('-', '').encode()).hexdigest()
    assert code not in str(rows(app, 'events'))
    recipient = app.test_client()
    result = redeem(recipient, code)
    assert result.data == b'Private project notes'
    assert result.headers['Content-Disposition'].startswith('attachment')
    assert redeem(recipient, code).status_code == 404
    assert rows(app, 'events')[-1]['action'] == 'Shared file downloaded'


@pytest.mark.parametrize('action', ['expire', 'revoke', 'delete'])
def test_unusable_codes(app, action):
    owner = account(app)
    upload(owner)
    identity = rows(app)[0]['id']
    code = share(owner, identity)
    digest = rows(app, 'shares')[0]['token_hash']
    if action == 'expire':
        with sqlite3.connect(Path(app.config['DATA_DIR']) / 'vault.sqlite3') as db:
            db.execute('UPDATE shares SET expires_at=0')
    elif action == 'revoke':
        post(owner, f'/shares/{digest}/revoke')
    else:
        post(owner, f'/files/{identity}/delete')
        assert not rows(app, 'shares')
    assert redeem(app.test_client(), code).status_code == 404


def test_share_owner_isolation_and_csrf(app):
    owner = account(app)
    upload(owner)
    identity = rows(app)[0]['id']
    code = share(owner, identity)
    digest = rows(app, 'shares')[0]['token_hash']
    other = account(app, 'bob')
    assert post(other, f'/files/{identity}/share').status_code == 404
    assert post(other, f'/shares/{digest}/revoke').status_code == 404
    assert b'notes.txt' not in other.get('/shares').data
    assert other.post('/receive', data={'code': code}).status_code == 400


def test_concurrent_redemption_is_single_use(app):
    owner = account(app)
    upload(owner)
    code = share(owner, rows(app)[0]['id'])
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: redeem(app.test_client(), code), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 404]


def test_corrupt_share_does_not_consume_code(app):
    owner = account(app)
    upload(owner)
    identity = rows(app)[0]['id']
    code = share(owner, identity)
    (Path(app.config['DATA_DIR']) / 'vault' / identity).write_bytes(b'bad')
    assert redeem(app.test_client(), code).status_code == 409
    assert rows(app, 'shares')[0]['used_at'] is None


def test_private_image_preview(app):
    owner = account(app)
    raw = io.BytesIO()
    Image.new('RGB', (10, 10), 'blue').save(raw, 'PNG')
    upload(owner, 'sample.png', raw.getvalue())
    identity = rows(app)[0]['id']
    assert owner.get(f'/files/{identity}/preview').mimetype == 'image/png'
    assert account(app, 'bob').get(f'/files/{identity}/preview').status_code == 404


def test_file_count_limit(app):
    owner = account(app)
    with sqlite3.connect(Path(app.config['DATA_DIR']) / 'vault.sqlite3') as db:
        db.executemany('INSERT INTO files(id,owner_id,name,size,mime,sha256,scan) VALUES(?,?,?,?,?,?,?)',
                       [(f'test-{i}', 1, f'note{i}.txt', 1, 'text/plain', 'test', 'Not scanned') for i in range(200)])
    result = upload(owner)
    assert b'200-file limit' in result.data
    assert len(rows(app)) == 200


def test_unknown_and_malformed_codes(app):
    recipient = app.test_client()
    assert redeem(recipient, 'bad-code').status_code == 400
    assert redeem(recipient, 'A'*24).status_code == 404
