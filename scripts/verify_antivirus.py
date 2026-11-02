"""Verify local ClamAV with benign bytes and the standard EICAR test string via stdin."""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import _find_clamscan

root=Path(__file__).resolve().parents[1]
scanner=_find_clamscan()
if not scanner:raise SystemExit('ClamAV is not installed or configured.')
database=Path(scanner).parent/'database'
arguments=[scanner,'--no-summary']
if database.is_dir():arguments.append('--database='+str(database))
arguments.append('-')
test_string=b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$' + b'EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
assert hashlib.sha256(test_string).hexdigest()=='275a021bbfb6489e54d471899f7db9d1663fc695ec2fe2a2c4538aabf651fd0f'
results={}
for name,payload,expected in [('benign',b'Harmless SecureVault verification fixture.',0),('eicar',test_string,1)]:
    run=subprocess.run(arguments,input=payload,capture_output=True,timeout=60)
    results[name]={'expected_exit_code':expected,'actual_exit_code':run.returncode,'passed':run.returncode==expected,
                   'diagnostic':run.stderr.decode(errors='replace')[:500] if run.returncode==2 else ''}
with tempfile.TemporaryDirectory(prefix='clamav-fixture-',dir=root/'instance') as folder:
    fixture=b'SecureVault harmless custom signature fixture.'
    database=Path(folder)/'test.hdb'
    database.write_text(f'{hashlib.md5(fixture,usedforsecurity=False).hexdigest()}:{len(fixture)}:SecureVault.TestFixture\n')
    run=subprocess.run([scanner,'--no-summary','--database='+str(database),'-'],input=fixture,capture_output=True,timeout=60)
    results['custom_signature']={'expected_exit_code':1,'actual_exit_code':run.returncode,'passed':run.returncode==1}
version=subprocess.run([scanner,'--version'],capture_output=True,timeout=10).stdout.decode().strip()
report={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'engine':version,'checks':results,'scope':'Benign and custom-signature checks verify integration; EICAR result is separately recorded and may be inconclusive. Not a detection benchmark.'}
(root/'docs'/'antivirus-results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
raise SystemExit(0 if results['benign']['passed'] and results['custom_signature']['passed'] else 1)
