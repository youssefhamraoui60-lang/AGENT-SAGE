"""Memory dialogue and explicit review, isolated from all Sage write approvals."""
import re
from uuid import UUID,uuid4
from psycopg.types.json import Jsonb
from app.services import learning,business_store as db,sage_crud as crud
from app.services.chat_turns import norm

def propose(owner,conversation,content,kind='preference',payload=None):
    payload={**(payload or {}),'conversation_id':str(conversation)}
    if payload.get('feedback_message_id'):
        content=learning.clean(content)
        if learning.INJECTION.search(content) or learning.VOLATILE.search(content):raise crud.CrudError('Cette réponse ne peut pas devenir une règle durable.',422)
        # Identical wording in two answers must not silently validate both contexts.
        fingerprint=learning.digest(learning.normalized(content)+'|feedback:'+str(payload['feedback_message_id']))
        with db.connection() as conn:
            learning.ensure(conn)
            return conn.execute('''INSERT INTO learning_items(id,owner_id,kind,title,content,source,payload,sha256)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(owner_id,kind,sha256)
                DO UPDATE SET title=learning_items.title RETURNING *''',
                (uuid4(),owner,kind,'Correction proposée',content,'chat:'+str(conversation),Jsonb(payload),fingerprint)).fetchone()
    return learning.create_item(owner,kind,'Règle proposée' if kind!='correction' else 'Correction proposée',content,'chat:'+str(conversation),payload)

def feedback_proposal(owner,conversation,message_id,verdict,expected=''):
    with db.connection() as conn:
        learning.ensure(conn)
        message=conn.execute("SELECT m.content FROM chat_messages m JOIN chat_conversations c ON c.id=m.conversation_id WHERE m.id=%s AND m.conversation_id=%s AND c.owner_id=%s AND m.role='assistant'",(message_id,conversation,owner)).fetchone()
        if not message:raise crud.CrudError('Réponse introuvable.',404)
        user=conn.execute("SELECT content FROM chat_messages WHERE conversation_id=%s AND role='user' AND id<%s ORDER BY id DESC LIMIT 1",(conversation,message_id)).fetchone()
    if verdict not in ('correct','incorrect') or not user:raise crud.CrudError('Retour invalide.',422)
    target=learning.clean(expected if verdict=='incorrect' else message['content'])
    if learning.VOLATILE.search(user['content']+' '+target):
        learning.feedback(owner,message_id,verdict,expected=target,confirm=True)
        publish(owner,conversation,'Votre retour est enregistré. Les valeurs actuelles de Sage ne sont pas mémorisées comme des règles.')
        return read_chat(owner,conversation)
    item=propose(owner,conversation,target,'correction',{'feedback_message_id':message_id,'verdict':verdict,
        'input_normalized':learning.normalized(user['content']),'target':target})
    publish(owner,conversation,'Je vous propose de mémoriser cette correction. Vous pouvez la valider, la modifier ou la refuser.',[item])
    return read_chat(owner,conversation)

def read_chat(owner,conversation):
    from app.services import conversation_chat as chat
    return chat.read(owner,conversation)

def feedback_id(item):
    value=item['payload'].get('feedback_message_id')
    if not value and item['source'].startswith('chat-message:'):
        try:value=int(item['source'].split(':',1)[1])
        except ValueError:pass
    return value

def publish(owner,conversation,text,items=()):
    from app.services import conversation_chat as chat
    with db.connection() as conn:
        row=chat.get_row(conn,owner,conversation,True)
        state=row['state']
        if items:state['memory_focus']=str(items[-1]['id'])
        chat.save_conversation_context(conn,owner,conversation,state)
        chat.append(conn,conversation,'assistant',text,{'memory_items':[str(i['id']) for i in items],'memory_dialogue':True})
        conn.execute('UPDATE chat_conversations SET revision=revision+1 WHERE id=%s',(conversation,))

def action(owner,conversation,identifier,step,content='',sha='',confirm=False,emit=True):
    from app.services import conversation_chat as chat
    with db.connection() as conn:
        learning.ensure(conn);chat.get_row(conn,owner,conversation)
        item=conn.execute('SELECT * FROM learning_items WHERE id=%s AND owner_id=%s',(identifier,owner)).fetchone()
        if not item:raise crud.CrudError('Règle introuvable.',404)
        if sha!=item['sha256']:raise crud.CrudError('La règle a changé ; relisez sa version actuelle.',409)
    if step=='edit':
        if item['status'] not in ('pending','validated'):raise crud.CrudError('Cette règle n’est plus modifiable.',409)
        payload={**item['payload'],'target':content}
        if item['status']=='validated':payload['replaces_id']=str(item['id'])
        updated=propose(owner,conversation,learning.clean(content),item['kind'],payload)
        if updated['id']!=item['id'] and item['status']=='pending':learning.review(owner,item['id'],'superseded')
        if not emit:return {'text':'Voici la règle modifiée. Elle attend votre validation.','items':[updated]}
        publish(owner,conversation,'Voici la règle modifiée. Elle attend votre validation.',[updated])
    else:
        if confirm is not True:raise crud.CrudError('Confirmez explicitement votre choix.',422)
        if step not in ('validate','reject','forget'):raise crud.CrudError('Action mémoire inconnue.',422)
        if step in ('validate','reject') and item['status']!='pending':raise crud.CrudError('Cette proposition a déjà été traitée.',409)
        if step=='validate':
            payload=item['payload']
            if payload.get('feedback_message_id'):
                learning.feedback(owner,payload['feedback_message_id'],payload['verdict'],expected=payload['target'],confirm=True)
            learning.review(owner,item['id'],'validated')
            for conflict in payload.get('conflicts_with',[]):learning.review(owner,UUID(conflict),'superseded')
            if payload.get('replaces_id') and payload['replaces_id']!=str(item['id']):learning.review(owner,UUID(payload['replaces_id']),'superseded')
            text='Cette règle est mémorisée. Elle pourra être réutilisée dans vos prochaines conversations.'
        elif step=='reject':learning.review(owner,item['id'],'rejected');text='Cette proposition est refusée. Elle ne sera pas utilisée.'
        else:
            learning.review(owner,item['id'],'superseded')
            # Feedback-derived examples must stop retrieval and future dataset exports too.
            message_id=feedback_id(item)
            if message_id:
                with db.connection() as conn:
                    conn.execute("UPDATE learning_items SET status='superseded' WHERE owner_id=%s AND (source=%s OR payload->>'feedback_message_id'=%s)",(owner,'chat-message:'+str(message_id),str(message_id)))
            text='Cette règle a été oubliée. Elle ne sera plus utilisée.'
        if not emit:return {'text':text,'items':[item]}
        publish(owner,conversation,text,[item])
    return read_chat(owner,conversation)

def turn(owner,conversation,text):
    """Returns a response descriptor, not a Sage execution instruction."""
    normalized=norm(text).strip();simple=re.sub(r'[^\w\s]',' ',normalized);simple=' '.join(simple.split())
    if simple in ('bilan de l apprentissage','bilan des erreurs','quelles sont tes faiblesses','bilan des ameliorations'):
        with db.connection() as conn:
            errors=conn.execute('SELECT family,count(*) AS n FROM learning_corrections WHERE owner_id=%s GROUP BY family ORDER BY n DESC',(owner,)).fetchall()
            methods=conn.execute('SELECT DISTINCT ON(family) family,status,evaluation FROM learning_auto_methods WHERE owner_id=%s ORDER BY family,version DESC',(owner,)).fetchall()
        lines=['Erreurs confirmées : '+str(sum(r['n'] for r in errors))+'.']
        for method in methods:
            evaluation=method['evaluation']
            lines.append(method['family']+' : '+method['status']+(' ; erreurs sur les cas indépendants : '+str(evaluation['before_errors'])+' → '+str(evaluation['after_errors']) if 'before_errors' in evaluation else ' ; méthode supplémentaire à examiner techniquement.'))
        return {'text':'\n'.join(lines)+'\nCes résultats concernent les tests de chaque méthode, pas toutes les conversations. Mémoire et méthodes évaluées ; aucun réentraînement automatique de Qwen et aucune autorisation Sage.', 'items':[]}
    if simple in ('qu as tu appris de mes corrections','mes corrections retenues','quelles corrections as tu retenues'):
        with db.connection() as conn:
            lessons=conn.execute('SELECT family,lesson FROM learning_corrections WHERE owner_id=%s ORDER BY created_at DESC LIMIT 8',(owner,)).fetchall()
        lines=[]
        for row in lessons:
            interpretation=row['lesson']['correct_interpretation']
            lines.append('Affectation corrigée vers le champ '+interpretation['field']+' ; aucune valeur fournisseur mémorisée comme défaut.' if isinstance(interpretation,dict) else interpretation)
        return {'text':('Voici les leçons de vos corrections :\n'+'\n'.join(str(i+1)+'. '+line for i,line in enumerate(dict.fromkeys(lines)))+'\nCes exemples guident les prochaines réponses. Seules les méthodes évaluées peuvent être activées automatiquement.' if lines else 'Aucune leçon de correction enregistrée pour le moment.'),'items':[]}
    if simple in ('quelles methodes as tu apprises','mes methodes apprises','mes ameliorations automatiques'):
        with db.connection() as conn:
            rows=conn.execute('SELECT id,family,version,status,evaluation FROM learning_auto_methods WHERE owner_id=%s ORDER BY created_at DESC LIMIT 20',(owner,)).fetchall()
            conn.execute("UPDATE chat_conversations SET state=jsonb_set(state,'{automatic_method_selection}',%s) WHERE id=%s AND owner_id=%s",(Jsonb([str(r['id']) for r in rows]),conversation,owner))
        labels={'typed_explicit_correction_v1':'Corrections de champs avec fautes de frappe','explicit_location_relation':'Distinction entre ville et adresse','new_draft_intent':'Nouvelle demande indépendante','repeated_question':'Informations déjà fournies','case_specific_edit':'Correction ponctuelle'}
        statuses={'active':'active','candidate':'à examiner','disabled':'désactivée','rejected':'non retenue'}
        return {'text':('Voici vos méthodes :\n'+'\n'.join(str(i+1)+'. '+labels.get(r['family'],'Méthode candidate')+' — version '+str(r['version'])+' — '+statuses.get(r['status'],r['status']) for i,r in enumerate(rows))+'\nElles améliorent le dialogue sans réentraîner le modèle. Dites « Désactive la méthode 1 » pour revenir au comportement précédent.' if rows else 'Aucune méthode automatique pour le moment.'),'items':[]}
    rollback=re.fullmatch(r'(?:desactive|annule)\s+la\s+methode\s+(\d+)[.!]?',normalized)
    if rollback:
        from app.services import conversation_chat as chat
        from app.services.learning_auto import disable
        with db.connection() as conn:ids=chat.get_row(conn,owner,conversation)['state'].get('automatic_method_selection',[])
        index=int(rollback[1])-1
        if not 0<=index<len(ids):return {'text':'Demandez « Quelles méthodes as-tu apprises ? », puis indiquez le numéro.','items':[]}
        disable(owner,UUID(ids[index]))
        return {'text':'Cette méthode est désactivée. Le comportement précédent est rétabli ; vos fiches Sage restent inchangées.','items':[]}
    match=re.match(r'^(?:retiens|memorise)\s+(?:que\s+)?(.+)$',normalized,re.S)
    if match:
        # Keep the user's spelling/capitalization in the proposed rule.
        original=re.match(r'^(?:retiens|mémorise|memorise)\s+(?:que\s+)?(.+)$',text.strip(),re.I|re.S)
        from app.services.learning_preferences import personal,conflicts
        content=original[1]
        explicit_personal=personal(content)
        competing=conflicts(owner,content) if explicit_personal else []
        item=propose(owner,conversation,content,payload={'scope':'personal' if explicit_personal else 'folder_TEST','validation_source':'explicit_user_request','conflicts_with':[str(r['id']) for r in competing]})
        if item['status']=='validated':return {'text':'Cette règle est déjà mémorisée.','items':[item]}
        if explicit_personal and not competing:
            item=learning.review(owner,item['id'],'validated')
            return {'text':'Je retiens cette préférence : '+content+'\nVous pouvez me demander de la modifier ou de l’oublier.','items':[item]}
        return {'text':('Cette préférence diffère de votre règle actuelle : '+competing[0]['content']+'\n' if competing else '')+'Proposition : '+content+'\nDites « Valide cette règle », « Modifie cette règle : … » ou « Refuse cette règle ».','items':[item]}
    correction=re.match(r'^(?:correction|je corrige(?: ta réponse)?|corrige ta réponse)\s*:\s*(.+)$',text.strip(),re.I|re.S)
    if correction:
        with db.connection() as conn:
            from app.services import conversation_chat as chat
            current=chat.get_row(conn,owner,conversation)['state']
            # A correction of the open business draft is an edit, not a memory command.
            if (current.get('articles') or current.get('partners')) and re.search(r'\b(?:nom|ville|adresse|ice|if|rc|telephone|paiement|montant|unite|site|categorie|designation|tva|devise)\b',norm(correction[1])):return None
            message=conn.execute("SELECT id FROM chat_messages WHERE conversation_id=%s AND role='assistant' AND COALESCE(payload->>'memory_dialogue','false')<>'true' ORDER BY id DESC LIMIT 1",(conversation,)).fetchone()
            original=conn.execute("SELECT content FROM chat_messages WHERE conversation_id=%s AND role='user' AND id<%s ORDER BY id DESC LIMIT 1",(conversation,message['id'])).fetchone() if message else None
        if not message or not original:return {'text':'Quelle réponse souhaitez-vous corriger ? Indiquez la correction attendue dans votre message.','items':[]}
        item=propose(owner,conversation,correction[1],'correction',{'feedback_message_id':message['id'],'verdict':'incorrect','input_normalized':learning.normalized(original['content']),'target':correction[1]})
        return {'text':'Correction proposée : '+correction[1]+'\nDites « Valide cette règle », « Modifie cette règle : … » ou « Refuse cette règle ».','items':[item]}
    listing=simple in ('que sais tu de moi','quelles regles as tu retenues','quelles regles as tu memorisees','mes regles','mes preferences','quelles sont mes regles en attente','mes regles en attente','mes propositions')
    if listing:
        with db.connection() as conn:
            learning.ensure(conn)
            pending='en attente' in simple or simple=='mes propositions'
            items=conn.execute("SELECT * FROM learning_items WHERE owner_id=%s AND status=%s AND kind IN ('preference','rule','correction','example') ORDER BY created_at DESC LIMIT 60",(owner,'pending' if pending else 'validated')).fetchall()
            grouped={}
            for item in items:
                key='feedback:'+str(feedback_id(item)) if feedback_id(item) else str(item['id'])
                if key not in grouped or item['payload'].get('feedback_message_id'):grouped[key]=item
            items=list(grouped.values())[:30]
            conn.execute('UPDATE chat_conversations SET state=jsonb_set(state,%s,%s) WHERE id=%s AND owner_id=%s',('{memory_selection}',Jsonb([str(i['id']) for i in items]),conversation,owner))
            conn.execute("UPDATE chat_conversations SET state=state-'memory_focus' WHERE id=%s AND owner_id=%s",(conversation,owner))
        return {'text':(('Voici vos propositions en attente :' if pending else 'Voici vos règles mémorisées :')+'\n'+'\n'.join(str(i+1)+'. '+r['content'] for i,r in enumerate(items))+'\nPour en retirer une, dites « Oublie la règle 1 ».' if items else 'Aucune règle correspondante pour le moment.'),'items':items,'listing':True}
    command=re.fullmatch(r"(oublie(?:r)?|valide(?:r)?|refuse(?:r)?|modifie(?:r)?)\s+(?:cette|la)\s+regle(?:\s+(\d+))?(?:\s*:\s*(.+))?[.!\s]*",normalized,re.S)
    if command:
        with db.connection() as conn:
            from app.services import conversation_chat as chat
            state=chat.get_row(conn,owner,conversation)['state'];ids=state.get('memory_selection',[])
            identifier=ids[int(command[2])-1] if command[2] and 0<int(command[2])<=len(ids) else (state.get('memory_focus') if not command[2] else None)
            if not identifier:return {'text':'Quelle règle souhaitez-vous traiter ? Indiquez son numéro dans la dernière liste.','items':[]}
            item=conn.execute('SELECT * FROM learning_items WHERE id=%s AND owner_id=%s',(UUID(identifier),owner)).fetchone()
        if not item:return {'text':'Cette règle est introuvable. Demandez « Quelles règles as-tu retenues ? ».','items':[]}
        step='forget' if command[1].startswith('oubl') else 'validate' if command[1].startswith('valid') else 'reject' if command[1].startswith('refus') else 'edit'
        if step=='edit' and not command[3]:return {'text':'Indiquez la nouvelle formulation après « Modifie cette règle : … ».','items':[item]}
        new_content=text.strip()[command.start(3):command.end(3)] if command[3] else ''
        return action(owner,conversation,item['id'],step,new_content,item['sha256'],confirm=True,emit=False)
    return None
