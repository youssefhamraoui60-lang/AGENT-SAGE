"""Repeated corrections are evidence to review, never automatically accepted facts."""
import re
from uuid import uuid4
from psycopg.types.json import Jsonb
from app.services import business_store as db,learning
from app.services.chat_turns import norm

def record(owner,conversation,before,after,text):
    from app.services.learning_corrections import record as record_typed
    record_typed(owner,conversation,before,after,text)
    # The deterministic controller can understand a natural correction outside
    # the typed grammar. Record its grounded field change as a candidate example;
    # this does not validate a general rule or train the model.
    correction=(after.get('_supplier_dialogue') or {}).pop('explicit_correction',None)
    if correction and correction['field'] in ('nom','ville'):
        previous=before.get('partners',[]);current=after.get('partners',[])
        if len(previous)==len(current)==1 and previous[0]['id']==current[0]['id'] and previous[0].get(correction['field'])==correction['before'] and current[0].get(correction['field'])==correction['value']:
            record_typed(owner,conversation,before,after,'corrige le '+correction['field']+' : '+correction['value'])
    from app.services.learning_auto import record as record_example
    record_example(owner,conversation,before,after,text)
    if not re.search(r'\b(?:non|correction|corrige|plutot|remplace)\b',norm(text)):return
    old=before.get('partners',[]);new=after.get('partners',[])
    if len(old)!=1 or len(new)!=1 or old[0]['id']!=new[0]['id']:return
    for field in ('nom','adresse','ville','ice','telephone','conditions_paiement','type_montant'):
        if old[0].get(field)==new[0].get(field):continue
        content='Correction de lecture du champ '+field+' : prendre en compte la dernière précision explicite de l’utilisateur, sans modifier les autres champs.'
        with db.connection() as conn:
            conn.execute("""INSERT INTO learning_items(id,owner_id,kind,title,content,source,payload,sha256)
              VALUES(%s,%s,'correction','Signal de correction à relire',%s,%s,%s,%s)
              ON CONFLICT(owner_id,kind,sha256) DO UPDATE SET payload=jsonb_set(learning_items.payload,'{occurrences}',to_jsonb(COALESCE((learning_items.payload->>'occurrences')::int,0)+1))""",
              (uuid4(),owner,content,'chat:'+str(conversation),Jsonb({'scope':'personal','occurrences':1,'signal_only':True,'field':field,'training_performed':False}),learning.digest('task-signal:'+field)))
