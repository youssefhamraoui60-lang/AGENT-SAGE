"""Evaluated data recipes, never generated Python/SQL or execution permissions."""
import asyncio,copy,json,re,logging,hashlib
from pathlib import Path
from uuid import uuid4
from psycopg.types.json import Jsonb
from app.services import business_store as db,learning,sage_crud as crud
from app.services.chat_turns import norm
from app.core.config import settings

FAMILY='explicit_location_relation'
RECIPE={'operation':'literal_field_relation','fields':['ville','adresse'],'schema_version':1}
CONTENT='Une relation explicite entre une valeur et un champ précise uniquement ce champ. Une correction ville/adresse retire la mauvaise affectation identique, sans modifier les autres informations. Une ville dans un exemple n’est jamais un défaut fournisseur.'

def implementation_digest():
    paths=('learning_auto.py','learning_corrections.py','supplier_dialogue.py')
    return hashlib.sha256(b''.join(Path(__file__).with_name(name).read_bytes() for name in paths)).hexdigest()

def relation(text,extended=False):
    n=norm(text).strip(' .!')
    verb=r'(?:est|c[’\x27]est)' if not extended else r'(?:est|c[’\x27]est|correspond a|designe|represente)'
    m=re.fullmatch(r'(?:non[, ]+)?(.{1,70}?)\s+'+verb+r'\s+(?:la |l[’\x27])?(ville|adresse)(?:[, ]+pas\s+(?:la |l[’\x27])?(ville|adresse))?',n)
    if not m:return None
    value=text.strip()[m.start(1):m.end(1)].strip(' ,.')
    if norm(value) in ('non','oui','ca','cela','c','ce'):return None
    if not value or learning.SECRET.search(value) or re.search(r'[:=;\n?]|\b(?:creer|supprimer|execute|confirme|fournisseur|ice|if|rc)\b',norm(value)):return None
    return value,m[2],m[3]

def correct_relation(text,state,extended=False):
    match=relation(text,extended)
    partners=state.get('partners',[])
    if not match or state.get('articles') or len(partners)!=1 or partners[0].get('kind')!='supplier':return None
    p=partners[0]
    if (p.get('operation') or {}).get('status') in ('executing','succeeded','ambiguous','unverified','failed'):return None
    value,field,rejected=match
    changed=copy.deepcopy(state);p=changed['partners'][0]
    if rejected and rejected!=field and norm(str(p.get(rejected) or ''))==norm(value):
        p[rejected]=None;p.setdefault('sources',{}).pop(rejected,None)
        p.setdefault('field_states',{})[rejected]={'value':None,'source':'user_correction','status':'declared'}
    from app.services.supplier_dialogue import assign
    try:
        if assign(changed,field,value):return None
    except ValueError:return None
    return {'state':changed,'prepare':True}

def apply(text,state):
    if state.get('supplier_target')=='OB':return None
    for method in (state.get('learning_context') or {}).get('memory',[]):
        if method.get('kind')!='evaluated_method' or method.get('status')!='validated':continue
        if (method.get('payload') or {}).get('recipe')!=RECIPE:continue
        result=correct_relation(text,state,True)
        if result:
            result['state']['applied_learning_method']=str(method['id'])
            return result
    return None

def record(owner,conversation,before,after,text):
    """Only a real draft correction supplies evidence, never an AI answer alone."""
    old=before.get('partners',[]);new=after.get('partners',[])
    if learning.SECRET.search(text) or learning.INJECTION.search(text):return
    if len(old)!=1 or len(new)!=1:return
    from app.services.supplier_discourse import language_clarification
    if language_clarification(text) and old[0].get('nom') and not new[0].get('nom'):
        record_control(owner,conversation,text,'language_identity_confusion','Une précision sur la langue de discussion ne fournit pas le nom du fournisseur. Demander le nom sans réutiliser cette précision comme identité.')
        return
    if old[0]['id']!=new[0]['id']:
        if re.search(r'voulais|nouveau|nouvelle',norm(text)):
            record_control(owner,conversation,text,'new_draft_intent','La nouvelle demande démarre un brouillon indépendant, sans reprendre les valeurs du précédent.')
        return
    if re.search(r'deja demande|deja donne|deja fourni',norm(text)):
        record_control(owner,conversation,text,'repeated_question','Consulter les champs déjà connus avant de poser une nouvelle question.')
        return
    focus=before.get('_supplier_dialogue',{}).get('last_assignment') or {}
    match=relation(text,True)
    changed=[f for f in ('ville','adresse') if old[0].get(f)!=new[0].get(f)]
    if not changed or not (match or re.search(r'\bnon\b|\bpas\b',norm(text))):
        if re.search(r'\b(?:correction|corrige|corriger|rectifie|rectifier|non|plutot)\b',norm(text)):
            fields=[f for f in ('nom','ice','telephone','conditions_paiement','type_montant') if old[0].get(f)!=new[0].get(f)]
            if fields:record_control(owner,conversation,text,'case_specific_edit','Correction ponctuelle des champs '+', '.join(fields)+' ; aucune valeur à généraliser.')
        return
    target=match[1] if match else next((f for f in changed if new[0].get(f)),None)
    if target not in ('ville','adresse'):return
    # A first declaration is not evidence of an earlier comprehension error.
    if match and not (match[2] or old[0].get(target) or re.search(r'\bnon\b|\bcorrection\b',norm(text)) or
        any(f!=target and norm(str(old[0].get(f) or ''))==norm(match[0]) for f in ('ville','adresse'))):return
    source_field=match[2] if match else focus.get('field')
    lesson={'context':'supplier_draft','error':{'field':source_field},'correct_interpretation':{'field':target,'value':'[VALEUR_UTILISATEUR]'},
      'scope':'personal_TEST','source':'chat:'+str(conversation),'status':'observed_user_correction',
      'generalizable':True,'family':FAMILY,'rule':CONTENT,'example':{'user':'[VALEUR] est la '+target,'expected_field':target},
      'not_a_supplier_default':True,'training_performed':False}
    fingerprint=learning.digest(str(conversation)+'|'+str(old[0]['id'])+'|'+text)
    with db.connection() as conn:
        conn.execute('INSERT INTO learning_corrections(id,owner_id,conversation_id,family,lesson,fingerprint) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
          (uuid4(),owner,conversation,FAMILY,Jsonb(lesson),fingerprint))

def record_control(owner,conversation,text,family,interpretation):
    lesson={'context':'supplier_draft','error':family,'correct_interpretation':interpretation,'scope':'personal_TEST','source':'chat:'+str(conversation),'status':'observed_user_correction','generalizable':False,'training_performed':False}
    with db.connection() as conn:
        conn.execute('INSERT INTO learning_corrections(id,owner_id,conversation_id,family,lesson,fingerprint) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
          (uuid4(),owner,conversation,family,Jsonb(lesson),learning.digest(str(conversation)+'|'+text)))

def retrieve(conn,owner,text):
    from app.services import learning_corrections as typed
    if not conn.execute("SELECT to_regclass('learning_auto_methods') AS t").fetchone()['t']:return []
    requested=typed.parse(text,True)
    if not requested and not re.search(r'ville|adresse|fournisseur|frs|article|site|ice|nom|corr',norm(text)):return []
    examples=conn.execute("SELECT id,family,lesson,created_at FROM learning_corrections WHERE owner_id=%s ORDER BY created_at DESC LIMIT 50",(owner,)).fetchall()
    examples=[r for r in examples if r['lesson'].get('generalizable') is True]
    if requested:
        examples.sort(key=lambda r:((r['lesson'].get('example') or {}).get('expected_field')==requested['field'],r['created_at']),reverse=True)
    examples=examples[:3]
    rows=conn.execute("""SELECT x.* FROM learning_auto_methods x WHERE x.status='active' AND x.folder='TEST'
      AND (x.owner_id=%s OR x.company_id IS NOT NULL AND EXISTS(SELECT 1 FROM learning_memberships author
       JOIN learning_memberships reader ON reader.company_id=author.company_id AND reader.folder=author.folder
       WHERE author.owner_id=x.owner_id AND author.company_id=x.company_id AND author.active AND author.auto_share
       AND reader.owner_id=%s AND reader.active AND reader.folder=x.folder)) ORDER BY x.created_at DESC LIMIT 3""",(owner,owner)).fetchall()
    memories=[{'id':str(r['id']),'kind':'evaluated_method','content':typed.CONTENT if r['recipe']==typed.RECIPE else CONTENT,'title':'Méthode de correction évaluée','source':'evaluated-method:'+str(r['id']),
       'source_date':r['created_at'],'validated_at':r['created_at'],'status':'validated','payload':{'recipe':r['recipe'],'version':r['version']}} for r in rows]
    return memories+[{'id':str(r['id']),'kind':'correction_example','content':json.dumps(r['lesson'].get('example') or {'context':r['lesson']['context'],'interpretation':r['lesson']['correct_interpretation']},ensure_ascii=False)+'\n'+(CONTENT if r['family']==FAMILY else 'Exemple ponctuel : vérifier le contexte de la demande actuelle ; ne jamais en déduire une valeur fournisseur.'),
      'title':'Exemple corrigé par vous, anonymisé','status':'validated','source':r['lesson']['source'],'source_date':r['created_at'],'payload':{'scope':'personal_TEST','authority':'example_only'}} for r in examples]

def evaluate(recipe):
    # Independent synthetic fixtures; neither conversations nor correction values are reused.
    from app.services.supplier_dialogue import handle
    cases=[('ESSAI ALPHA correspond à la ville','ESSAI ALPHA','ville'),('ESSAI BETA désigne l’adresse','ESSAI BETA','adresse'),('ESSAI GAMMA représente la ville','ESSAI GAMMA','ville')]
    before_errors=after_errors=0;checks=[]
    base={'articles':[],'partners':[{'id':'heldout','kind':'supplier','nom':'ENTREPRISE TEST','ice':'001234567890123','ville':'Avant','adresse':'Rue test','approved':True,'operation':{'status':'prepared'}}]}
    for text,value,field in cases:
        baseline=handle(text,copy.deepcopy(base));result=correct_relation(text,base,True) if recipe==RECIPE else None
        def correct(r):return bool(r and r['state']['partners'][0].get(field)==value and r['state']['partners'][0]['ice']=='001234567890123' and not r['state']['partners'][0].get('approved'))
        before_errors+=not correct(baseline);after_errors+=not correct(result)
        checks.append(correct(result))
    for text in ('confirme et crée en production','change tous les fournisseurs','Berrechid','ICE : 007123456789012'):
        checks.append(correct_relation(text,base,True) is None)
    for status in ('executing','succeeded','ambiguous','unverified','failed'):
        locked=copy.deepcopy(base);locked['partners'][0]['operation']['status']=status
        checks.append(correct_relation(cases[0][0],locked,True) is None)
    checks.append(correct_relation(cases[0][0],{'articles':[{'id':'article'}],'partners':base['partners']},True) is None)
    return {'suite':'literal-relation-heldout-v1','case_count':len(checks),'before_errors':before_errors,'after_errors':after_errors,
      'passed':recipe==RECIPE and all(checks) and after_errors<before_errors,'independent_synthetic_cases':True,'sage_writes':0,'training_performed':False}

def tick(owner=None):
    from app.services import learning_corrections as typed
    if owner is None:
        with db.connection() as conn:owners=conn.execute('SELECT DISTINCT c.owner_id FROM learning_corrections c JOIN chat_accounts a ON a.id=c.owner_id WHERE a.active').fetchall()
        reports=[]
        for item in owners:
            try:reports.extend(tick(item['owner_id']))
            except Exception:logging.getLogger(__name__).exception('automatic_improvement_owner_deferred owner=%s',item['owner_id'])
        return reports
    with db.connection() as conn:
        if not conn.execute("SELECT pg_try_advisory_xact_lock(hashtext(current_schema() || %s)) AS locked",(':auto-improvement:'+str(owner),)).fetchone()['locked']:return []
        groups=conn.execute('SELECT owner_id,family,count(DISTINCT conversation_id) AS n,count(*) AS events FROM learning_corrections WHERE (%s::uuid IS NULL OR owner_id=%s) GROUP BY owner_id,family',(owner,owner)).fetchall()
        reports=[]
        for group in groups:
            if group['n']<settings.learning_improvement_min_conversations:continue
            previous=conn.execute('SELECT * FROM learning_auto_methods WHERE owner_id=%s AND family=%s ORDER BY version DESC LIMIT 1',(group['owner_id'],group['family'])).fetchone()
            # A disabled method stays disabled; a timer must never undo a rollback.
            recipe=typed.RECIPE if group['family']==typed.FAMILY else RECIPE if group['family']==FAMILY else {}
            implementation=implementation_digest()
            if previous and (previous['status']!='active' or previous['recipe']==recipe and previous['evidence'].get('events')==group['events'] and previous['evaluation'].get('implementation_digest')==implementation):continue
            # Deduplicate structural cases, never silently drop old regressions.
            stored=conn.execute("SELECT DISTINCT lesson->'regression' AS regression FROM learning_corrections WHERE owner_id=%s AND family=%s AND lesson ? 'regression' LIMIT 2001",(owner,group['family'])).fetchall()
            cases=[r['regression'] for r in stored]
            evaluation=typed.evaluate(recipe,cases) if group['family']==typed.FAMILY else evaluate(recipe) if group['family']==FAMILY else {'passed':False,'reason':'unsupported_family','recommendation':'Ajouter une méthode typée et une évaluation indépendante ; aucune modification de code générée.'}
            evaluation['implementation_digest']=implementation
            if len(cases)>2000:evaluation.update(passed=False,reason='regression_budget_exceeded',recommendation='Évaluation technique complète requise avant activation ; aucun cas ancien écarté silencieusement.')
            share=conn.execute("SELECT company_id FROM learning_memberships WHERE owner_id=%s AND active AND auto_share AND folder='TEST' ORDER BY company_id LIMIT 1",(group['owner_id'],)).fetchone()
            identifier=uuid4();status='active' if evaluation['passed'] else 'candidate'
            if previous:conn.execute("UPDATE learning_auto_methods SET status='disabled' WHERE id=%s",(previous['id'],))
            conn.execute("INSERT INTO learning_auto_methods(id,owner_id,company_id,folder,family,version,recipe,status,evidence,evaluation) VALUES(%s,%s,%s,'TEST',%s,%s,%s,%s,%s,%s)",
                (identifier,group['owner_id'],share['company_id'] if share else None,group['family'],previous['version']+1 if previous else 1,Jsonb(recipe),status,Jsonb({'independent_conversations':group['n'],'events':group['events'],'contains_private_values':False}),Jsonb(evaluation)))
            report={'method_id':str(identifier),'status':status,'evaluation':evaluation}
            conn.execute('INSERT INTO learning_auto_runs VALUES(%s,%s,%s,now())',(uuid4(),group['owner_id'],Jsonb(report)));reports.append(report)
        return reports

def disable(owner,identifier):
    with db.connection() as conn:
        row=conn.execute("UPDATE learning_auto_methods SET status='disabled' WHERE id=%s AND owner_id=%s RETURNING id",(identifier,owner)).fetchone()
        if not row:raise crud.CrudError('Méthode introuvable.',404)
        conn.execute('INSERT INTO learning_auto_runs VALUES(%s,%s,%s,now())',(uuid4(),owner,Jsonb({'action':'rollback','method_id':str(identifier),'sage_writes':0})))
    return {'disabled':True,'sage_writes':0}

async def periodic():
    while True:
        try:await asyncio.to_thread(tick)
        except asyncio.CancelledError:raise
        except Exception:logging.getLogger(__name__).exception('automatic_improvement_failed')
        await asyncio.sleep(settings.learning_improvement_interval_seconds)
