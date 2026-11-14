"""Validated dataset lifecycle and periodic readiness checks. Never trains a GGUF."""
import asyncio,importlib.util,json,os,platform,shutil,subprocess,sys
from datetime import datetime,timezone
from functools import lru_cache
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from difflib import SequenceMatcher
import httpx
from psycopg.types.json import Jsonb
from app.services import business_store as db,learning
from app.core.config import settings

@lru_cache(maxsize=1)
def capability():
    packages={name:importlib.util.find_spec(name) is not None for name in ('torch','transformers','peft','bitsandbytes','datasets')}
    gpu=False
    if shutil.which('nvidia-smi'):
        try:gpu=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total','--format=csv,noheader'],capture_output=True,text=True,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).returncode==0
        except (OSError,subprocess.TimeoutExpired):pass
    models=[]
    try:
        with httpx.Client(timeout=3,trust_env=False) as client:models=client.get(settings.ollama_url+'/api/tags').json().get('models',[])
    except (httpx.HTTPError,ValueError):pass
    current=next((m for m in models if m.get('name')==settings.ollama_model),{})
    ram=None
    if os.name=='nt':
        import ctypes
        class Memory(ctypes.Structure):
            _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in ('physical','available','page','page_available','virtual','virtual_available','extended')]
        memory=Memory();memory.length=ctypes.sizeof(memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):ram=memory.physical
    return {'available':False,'cpu_threads':os.cpu_count(),'ram_bytes':ram,'free_disk_bytes':shutil.disk_usage(learning.ROOT).free,
        'python':sys.version.split()[0],'platform':platform.platform(),'nvidia_gpu_visible':gpu,
        'packages':packages,'model':settings.ollama_model,'digest':current.get('digest','unverified'),
        'format':current.get('details',{}).get('format','unknown'),
        'quantization':current.get('details',{}).get('quantization_level','unknown'),
        'missing':['Checkpoint source entraînable (le GGUF Ollama est destiné à l’inférence)',
            'Environnement Python/PyTorch/Transformers/PEFT compatible avec un accélérateur vérifié',
            'Accélérateur et mémoire suffisants à mesurer avant un entraînement 7B',
            'Entraîneur LoRA et banc d’évaluation indépendant avant toute activation'],
        'policy':'No training or model activation on this installation. Dataset preparation only.'}

def configure(owner,enabled,min_examples,interval_hours):
    with db.connection() as conn:
        learning.ensure(conn)
        conn.execute('''INSERT INTO learning_config(owner_id,enabled,min_examples,interval_hours) VALUES (%s,%s,%s,%s)
           ON CONFLICT(owner_id) DO UPDATE SET enabled=EXCLUDED.enabled,min_examples=EXCLUDED.min_examples,interval_hours=EXCLUDED.interval_hours''',
           (owner,enabled,min_examples,interval_hours))
    return {'enabled':enabled,'min_examples':min_examples,'interval_hours':interval_hours}

def build_examples(rows):
    groups={};excluded={'secret':0,'volatile_or_injection':0,'duplicate_or_near_duplicate':0,'conflicting_correction':0}
    for row in rows:
        user=row['user_text'].strip();target=row['expected'].strip();combined=user+'\n'+target
        if learning.SECRET.search(combined):excluded['secret']+=1;continue
        if learning.VOLATILE.search(combined) or learning.INJECTION.search(combined):excluded['volatile_or_injection']+=1;continue
        from app.services.learning_privacy import anonymize_pair
        user,target=anonymize_pair(user,target)
        combined=user+'\n'+target
        key=learning.normalized(user)
        groups.setdefault(key,[]).append((row,user,target))
    result=[];seen=[]
    for key,values in groups.items():
        if len({learning.normalized(v[2]) for v in values})!=1:excluded['conflicting_correction']+=len(values);continue
        row,user,target=values[0]
        if any(SequenceMatcher(None,key,previous).ratio()>=.93 for previous in seen):excluded['duplicate_or_near_duplicate']+=len(values);continue
        seen.append(key);excluded['duplicate_or_near_duplicate']+=len(values)-1
        # Conversation-level split: corrections from one conversation never cross the boundary.
        split='test' if int(learning.digest(str(row['conversation_id']))[:8],16)%5==0 else 'train'
        result.append({'messages':[{'role':'user','content':user},{'role':'assistant','content':target}],
            'split':split,'source_message_id':row['message_id'],'source_feedback_id':str(row['id']),
            'validated_at':str(row['created_at']),'validation':row.get('validation','explicit_user_feedback'),'task':'assistant_response',
            'conversation_group':learning.digest(str(row['conversation_id'])),'content_sha':learning.digest(combined)})
    return result,excluded

@contextmanager
def artifact_guard():
    created=[]
    try:yield created
    except BaseException:
        base=Path(settings.learning_dataset_directory).resolve()
        for path in created:
            resolved=path.resolve()
            if resolved.is_relative_to(base) and resolved.name in ('train.jsonl','test.jsonl','manifest.json'):resolved.unlink(missing_ok=True)
        raise

def export_dataset(owner,force=False):
    with artifact_guard() as written,db.connection() as conn:
        learning.ensure(conn)
        conn.execute('INSERT INTO learning_config(owner_id) VALUES (%s) ON CONFLICT DO NOTHING',(owner,))
        cfg=conn.execute('SELECT * FROM learning_config WHERE owner_id=%s FOR UPDATE',(owner,)).fetchone()
        if not force and (not cfg['enabled'] or cfg['last_job_at'] and (datetime.now(timezone.utc)-cfg['last_job_at']).total_seconds()<cfg['interval_hours']*3600):return {'status':'not_due','training_performed':False}
        rows=conn.execute('''SELECT f.id,f.expected,f.created_at,t.user_text,t.conversation_id,t.message_id
            FROM learning_feedback f JOIN learning_turns t ON t.id=f.turn_id
            WHERE f.owner_id=%s AND t.owner_id=%s AND f.confirmed=true AND t.eligible=true
            AND EXISTS(SELECT 1 FROM learning_items i WHERE i.owner_id=f.owner_id AND i.kind='example'
                       AND i.source='chat-message:' || t.message_id::text AND i.status='validated')
            ORDER BY f.created_at,f.id''',(owner,owner)).fetchall()
        # Explicit task corrections are anonymized at capture; no private draft is exported.
        corrections=conn.execute("SELECT * FROM learning_corrections WHERE owner_id=%s AND family IN (%s,%s) ORDER BY created_at",(owner,'explicit_location_relation','typed_explicit_correction_v1')).fetchall()
        for correction in corrections:
            example=correction['lesson'].get('example') or {}
            if not example.get('user') or example.get('expected_field') not in ('nom','ville','adresse','ice','identifiant_fiscal','rc','telephone','email','conditions_paiement','site','designation','unite','categorie'):continue
            rows.append({'id':correction['id'],'user_text':example['user'],'expected':'Affecter [VALEUR] uniquement au champ '+example['expected_field']+'. Ne pas utiliser cette valeur comme défaut.',
                'conversation_id':correction['conversation_id'],'message_id':None,'created_at':correction['created_at'],'validation':'explicit_user_task_correction'})
        examples,excluded=build_examples(rows)
        last=conn.execute('SELECT manifest FROM learning_jobs WHERE owner_id=%s ORDER BY created_at DESC LIMIT 1',(owner,)).fetchone()
        old_hashes=set(last['manifest'].get('example_hashes',[])) if last else set()
        new_count=sum(x['content_sha'] not in old_hashes for x in examples)
        if not force and new_count<cfg['min_examples']:return {'status':'waiting_for_validated_examples','count':len(examples),'new_count':new_count,'required':cfg['min_examples'],'training_performed':False}
        dataset_sha=learning.digest(json.dumps(examples,sort_keys=True,ensure_ascii=False))
        previous=conn.execute('SELECT * FROM learning_jobs WHERE owner_id=%s AND dataset_sha=%s ORDER BY created_at DESC LIMIT 1',(owner,dataset_sha)).fetchone()
        if previous:return {'status':previous['status'],'job_id':str(previous['id']),'manifest':previous['manifest'],'training_performed':False}
        output=Path(settings.learning_dataset_directory)/str(owner)/dataset_sha
        files={};bodies={}
        for split in ('train','test'):
            body=''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in examples if x['split']==split)
            path=output/(split+'.jsonl');bodies[path]=body;files[split]={'count':sum(x['split']==split for x in examples),'sha256':learning.digest(body),'path':str(path)}
        cap=capability();identifier=uuid4()
        manifest={'id':str(identifier),'dataset_sha':dataset_sha,'files':files,'excluded':excluded,'example_count':len(examples),
            'base_model':cap['model'],'base_digest':cap['digest'],'training_performed':False,'held_out_test_never_for_training':True,
            'automatic_activation':False,'missing':cap['missing'],'created_at':datetime.now(timezone.utc).isoformat()}
        manifest['privacy']={'structured_supplier_entities_replaced':True,'emails_and_long_numbers_replaced':True,'secret_examples_excluded':True,'manual_review_required_before_training':True}
        manifest['example_hashes']=[x['content_sha'] for x in examples]
        manifest['new_validated_examples']=new_count
        manifest['independent_test_available']=files['test']['count']>0 and files['train']['count']>0
        if not manifest['independent_test_available']:manifest['missing']=manifest['missing']+['Davantage de conversations indépendantes pour séparer entraînement et test']
        bodies[output/'manifest.json']=json.dumps(manifest,ensure_ascii=False,indent=2)
        artifact_bytes=sum(len(body.encode('utf-8')) for body in bodies.values())
        conn.execute('INSERT INTO learning_jobs(id,owner_id,dataset_sha,manifest,status,artifact_bytes) VALUES (%s,%s,%s,%s,%s,%s)',(identifier,owner,dataset_sha,Jsonb(manifest),'blocked_training_environment',artifact_bytes))
        conn.execute('UPDATE learning_config SET last_job_at=now() WHERE owner_id=%s',(owner,))
        conn.execute('''INSERT INTO learning_versions(id,owner_id,model_name,digest,status,metadata)
           VALUES (%s,%s,%s,%s,'baseline',%s) ON CONFLICT DO NOTHING''',
           (uuid4(),owner,cap['model'],cap['digest'],Jsonb({'source':'ollama_installed','dataset_sha':None,'activation_changed':False})))
        # All quota-checked database writes precede filesystem writes.
        output.mkdir(parents=True,exist_ok=True)
        for path,body in bodies.items():written.append(path);path.write_text(body,encoding='utf-8')
    return {'status':'blocked_training_environment','job_id':str(identifier),'manifest':manifest,'training_performed':False}

async def periodic():
    while True:
        await asyncio.sleep(60)
        try:
            def tick():
                with db.connection() as conn:
                    learning.ensure(conn);owners=conn.execute('SELECT owner_id FROM learning_config WHERE enabled=true').fetchall()
                for row in owners:export_dataset(row['owner_id'])
            await asyncio.to_thread(tick)
        except asyncio.CancelledError:raise
        except Exception:
            # A failed readiness check never changes the running model or Sage data.
            import logging
            logging.getLogger(__name__).warning('learning_periodic_check_failed')
