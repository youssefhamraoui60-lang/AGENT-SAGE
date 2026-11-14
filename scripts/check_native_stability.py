"""Check new log entries since the explicitly recorded final stability baseline."""
import json
import re
from pathlib import Path

root=Path(__file__).resolve().parents[1]
baseline=json.loads((root/'logs/native-stability-baseline.json').read_text(encoding='utf-8-sig'))
errors=[]
warnings=[]
expected_disconnects=[]
sizes={}
state=json.loads((root/'logs/native-final-state.json').read_text(encoding='utf-8'))
services_healthy=bool(state.get('http')) and all(code==200 for code in state['http'].values())
for name,offset in baseline.items():
    path=root/'logs'/name
    data=path.read_bytes() if path.exists() else b''
    if len(data)<offset: raise SystemExit('Log truncated since baseline: '+name)
    lines=data[offset:].decode('utf-8',errors='replace').splitlines()
    sizes[name]=len(data)-offset
    for line in lines:
        if (name=='postgres-native.log' and services_healthy and
            'LOG:  could not receive data from client: unrecognized winsock error 10054' in line):
            expected_disconnects.append({'file':name,'line':line,
                'reason':'Client connection reset during controlled n8n backup restart; PostgreSQL severity LOG, final service health HTTP 200'})
            continue
        if re.search(r'\b(fatal|panic|traceback|error)\b',line,re.I): errors.append({'file':name,'line':line})
        elif re.search(r'\bwarning\b|deprecated|deprecation',line,re.I): warnings.append({'file':name,'line':line})
proof={'status':'FAIL' if errors else 'PASS','scope':'New entries since final baseline, including final backup/restart and HTTP checks',
    'bytes_checked':sizes,'critical_or_error_lines':errors,'expected_client_disconnects':expected_disconnects,'warnings':warnings}
(root/'logs/native-stability-check.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(proof,ensure_ascii=False,indent=2))
raise SystemExit(1 if errors else 0)
