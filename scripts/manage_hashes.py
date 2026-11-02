"""Operator-only local SHA-256 denylist management. No file contents are transmitted."""
import argparse
import re
import sqlite3
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('action',choices=['add','remove','list'])
parser.add_argument('--sha256')
parser.add_argument('--label',default='Operator block')
parser.add_argument('--data-dir',type=Path,default=Path(__file__).resolve().parents[1]/'instance')
args=parser.parse_args()
database=args.data_dir/'vault.sqlite3'
if not database.is_file():parser.error('Start the application first to create the database.')
if args.action!='list' and not re.fullmatch('[0-9a-fA-F]{64}',args.sha256 or ''):
    parser.error('Provide a complete SHA-256 hexadecimal digest.')
with sqlite3.connect(database) as connection:
    if args.action=='add':
        connection.execute('INSERT OR REPLACE INTO blocked_hashes(sha256,label) VALUES(?,?)',(args.sha256.lower(),args.label[:100]))
    elif args.action=='remove':connection.execute('DELETE FROM blocked_hashes WHERE sha256=?',(args.sha256.lower(),))
    else:
        for row in connection.execute('SELECT sha256,label FROM blocked_hashes ORDER BY created_at'):print(*row)
