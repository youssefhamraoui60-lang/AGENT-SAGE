"""Compare a separately confirmed admin fingerprint; never trusts/imports or logs in."""
import argparse,hashlib,json,ssl,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--confirmed-sha256',required=True,help='Independent administrator-confirmed SHA256, not copied from network observation')
args=parser.parse_args()
expected=re.sub(r'[:\s-]','',args.confirmed_sha256).lower()
if not re.fullmatch('[0-9a-f]{64}',expected):raise SystemExit('Invalid SHA256 format')
file=ROOT/'runtime/sql-presented-certificate-0.pem'
actual=hashlib.sha256(ssl.PEM_cert_to_DER_cert(file.read_text(encoding='ascii'))).hexdigest()
matched=actual==expected
print(json.dumps({'match':matched,'certificate_file':str(file),'trust_imported':False,'sql_login_sent':False,'policy_enabled':False}))
if not matched:raise SystemExit(1)
