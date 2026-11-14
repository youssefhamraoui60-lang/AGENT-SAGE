import json
from pathlib import Path
import sys
import httpx
from test_ai import CASES
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.schemas.extraction import Extraction

response=httpx.post('http://127.0.0.1:8000/api/ai/extract',json={'demande':CASES[0]},timeout=240)
response.raise_for_status()
data=Extraction.model_validate(response.json())
assert data.unite is None and data.champs_manquants==['unite']
proof={'status':'PASS','http':response.status_code,'json':data.model_dump()}
(ROOT/'logs/backend-extraction-native-final.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(proof,ensure_ascii=False,indent=2))
