import base64,io,json,time,sys
from pathlib import Path
from PIL import Image
import httpx
p=Path('runtime/sob-improvements-20261113');mid=sys.argv[1] if len(sys.argv)>1 else '5371'
f=next((p/'attachments'/mid).glob('*'));im=Image.open(f);im.thumbnail((1100,1400));buf=io.BytesIO();im.save(buf,'JPEG',quality=90)
task=sys.argv[2] if len(sys.argv)>2 else 'Text Recognition:'
start=time.time()
with httpx.Client(timeout=180,trust_env=False) as c:
 r=c.post('http://127.0.0.1:11434/api/chat',json={'model':'glm-ocr','stream':False,'keep_alive':'2m','messages':[{'role':'user','content':task,'images':[base64.b64encode(buf.getvalue()).decode()]}],'options':{'temperature':0,'num_ctx':4096,'num_predict':1600}});r.raise_for_status();d=r.json()
(p/('glm-'+mid+('-table' if 'Table' in task else '')+'.json')).write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'seconds':time.time()-start,'result':d},ensure_ascii=True))
