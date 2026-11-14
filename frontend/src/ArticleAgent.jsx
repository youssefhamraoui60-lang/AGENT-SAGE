import React,{useEffect,useState} from 'react';

const labels={designation:'Désignation',code_article:'Code article proposé',categorie:'Catégorie',unite:'Unité stock / achat / vente',site:'Site à vérifier',fournisseur:'Fournisseur mentionné',code_fournisseur:'Code fournisseur',reference_article:'Article de référence à consulter',code_comptable:'Code comptable',gestion_stock:'Gestion stock — code Sage',gestion_lots:'Gestion lots — code Sage'};
const messages={duplicate_article_code:'Ce code article existe déjà dans TEST.',sql_check_unavailable:'SQL Server indisponible : vérification bloquée.',supplier_code_required:'Précisez le code du fournisseur mentionné.',supplier_link_mapping_requires_review:'Le lien fournisseur nécessite une revue du mapping métier ; aucune association ne sera créée automatiquement.',human_draft_validation_required:'Validez d’abord le brouillon.',sql_business_checks_failed:'Les contrôles SQL doivent être corrigés.',stale_draft_revision:'Ce brouillon a changé. Rechargez sa dernière révision.',security_conditions_not_met:'Création en attente de configuration Sage.',similar_designation_review_required:'Une désignation identique existe : examinez les références ci-dessous.'};
function explain(value){if(value.startsWith('missing:'))return 'Information manquante : '+(labels[value.split(':')[1]]||value);if(value.startsWith('unknown:'))return 'Valeur absente des référentiels TEST : '+(labels[value.split(':')[1]]||value);return messages[value]||value;}

export default function ArticleAgent({token}){
 const [text,setText]=useState('Crée un nouvel article Ciment CPJ35, catégorie NEG, unité SAC, pour le site 201.');
 const [session,setSession]=useState(null),[form,setForm]=useState({}),[dirty,setDirty]=useState(false),[history,setHistory]=useState([]),[busy,setBusy]=useState(''),[error,setError]=useState('');
 const [actor,setActor]=useState(''),[reason,setReason]=useState(''),[confirm,setConfirm]=useState(false),[nonce,setNonce]=useState('');
 async function api(path,options={}){
  const response=await fetch('/api/v1/article-agent/'+path,{...options,headers:{'Content-Type':'application/json','X-Approval-Token':token},cache:'no-store'});
  const data=await response.json();
  if(!response.ok)throw new Error(response.status===403?'Jeton d’accès local requis ou autorisation refusée.':response.status===423?'Création en attente de configuration Sage.':typeof data.detail==='string'?explain(data.detail):'Vérifiez les champs de la demande.');
  return data;
 }
 function accept(value){setSession(value);setForm(value.draft);setDirty(false);setNonce('');setConfirm(false);}
 async function loadHistory(){setHistory((await api('conversations')).conversations);}
 async function run(label,fn){setBusy(label);setError('');try{await fn();await loadHistory();}catch(e){setError(e.message);}finally{setBusy('');}}
 useEffect(()=>{setSession(null);setForm({});setNonce('');setHistory([]);setConfirm(false);setError('');},[token]);
 const path=session?'conversations/'+session.id:'';
 async function action(name){accept(await api(path+'/'+name,{method:'POST',body:JSON.stringify({revision:session.revision})}));}
 async function saveDraft(){accept(await api(path,{method:'PATCH',body:JSON.stringify({revision:session.revision,draft:form})}));}
 const operation=session?.operation;
 const immutable=operation&&!['prepared','blocked'].includes(operation.status);
 const ready=session?.security?.ready&&operation?.checks?.security?.ready;
 const validation=session?.validation;
 return <section className="article-agent" aria-label="Conversation agent IA">
  <div className="panel"><h2>Votre demande en français</h2><p>Décrivez un article. L’IA prépare une proposition ; elle ne crée aucune fiche automatiquement.</p>
   <form onSubmit={e=>{e.preventDefault();run('Analyse par Qwen en cours…',async()=>accept(await api('conversations',{method:'POST',body:JSON.stringify({message:text})})));}}>
    <label htmlFor="agent-message">Demande utilisateur<textarea id="agent-message" rows={4} value={text} maxLength={8000} onChange={e=>setText(e.target.value)} required/></label>
    <p className="hint">Ollama local · Qwen 2.5 7B · Ne saisissez aucun mot de passe. Les données SQL de contrôle ne sont pas envoyées au modèle.</p>
    <button disabled={!token||!!busy||text.trim().length<3}>Analyser ma demande</button>
   </form>
   {busy&&<p role="status" aria-live="polite">{busy} Les contrôles ne déclenchent aucune écriture Sage.</p>}
   {error&&<p role="alert" className="message">{error}</p>}
  </div>
  {session&&<>
   <div className="panel"><h2>Proposition de l’agent</h2><blockquote>{session.message}</blockquote>
    <p>Le code généré par l’application, si aucun code n’a été indiqué, est une proposition non réservée. Complétez les champs vides puis vérifiez les données.</p>
    {session.history?.[0]?.payload?.single_article_supported===false&&<p className="message">Cette conversation traite un seul article à la fois. Reformulez votre demande si elle concerne plusieurs objets.</p>}
    {session.history?.[0]?.payload?.questions?.map((q,i)=><p key={i} className="message">{q}</p>)}
    <details><summary>Extraction initiale et provenance IA</summary><pre>{JSON.stringify({extraction:session.initial_extraction,provenance:session.ai_provenance,source_du_code:session.history?.[0]?.payload?.application_generated_code?'Généré par l’application, non réservé':'Extrait de la demande'},null,2)}</pre></details>
    <div className="draft-grid">{Object.entries(labels).map(([key,label])=><label key={key}>{label}<input value={form[key]||''} disabled={!!busy||immutable} onChange={e=>{setForm({...form,[key]:e.target.value});setDirty(true);setNonce('');setConfirm(false);}} /></label>)}</div>
    <div className="agent-actions"><button disabled={!!busy||!dirty||immutable} onClick={()=>run('Enregistrement de la correction…',saveDraft)}>Enregistrer les corrections</button>
    <button disabled={!!busy||dirty||immutable} onClick={()=>run('Contrôles SQL en lecture seule…',()=>action('check'))}>Vérifier dans SQL Server</button>
    <button disabled={!!busy||dirty||immutable} onClick={()=>run('Validation du brouillon…',()=>action('validate'))}>Valider le brouillon</button></div>
    {dirty&&<p className="hint">Enregistrez les modifications avant de relancer les contrôles. Toute correction invalide la validation précédente.</p>}
    {!!validation?.errors?.length&&<ul className="message">{validation.errors.map(x=><li key={x}>{explain(x)}</li>)}</ul>}
    {validation?.valid&&<p className="message success">Référentiels SQL et code vérifiés. {session.validated?'Brouillon validé localement.':'Validation humaine du brouillon requise.'} Les contrôles métier conditionnels Sage restent distincts.</p>}
    {!!validation?.sql?.designation_matches?.length&&<div className="message">Désignation déjà présente : {validation.sql.designation_matches.map(r=>r.ITMREF_0).join(', ')}. Vérifiez qu’il ne s’agit pas du même article.</div>}
    {validation?.sql?.reference?.length>0&&<details><summary>Article de référence consulté</summary><pre>{JSON.stringify(validation.sql.reference,null,2)}</pre></details>}
    {validation?.sql?.category?.length>0&&<details><summary>Valeurs de catégorie constatées dans SQL</summary><pre>{JSON.stringify(validation.sql.category,null,2)}</pre><p>Aucune valeur n’est copiée automatiquement dans votre brouillon.</p></details>}
    <p className="hint">Le site est contrôlé ; ce parcours crée l’article uniquement. Une fiche article-site et une relation fournisseur nécessitent leur opération métier et leur approbation propres.</p>
   </div>
   <div className="panel"><h2>Préparation et approbation distincte</h2><p className="message">{session.creation_message}</p>
    <button disabled={!!busy||dirty||!session.validated||immutable} onClick={()=>run('Préparation SOAP sans envoi…',()=>action('prepare'))}>Préparer la création Sage</button>
    {operation&&<><p>Opération {operation.id} · État : {operation.status}</p><details><summary>Prévisualiser le XML et les contrôles</summary><pre className="xml-preview">{operation.object_xml}</pre><pre>{JSON.stringify(operation.checks,null,2)}</pre></details>
     <div className="draft-grid"><label>Nom du valideur<input value={actor} onChange={e=>{setActor(e.target.value);setConfirm(false);setNonce('');}}/></label><label>Motif d’approbation<input value={reason} onChange={e=>{setReason(e.target.value);setConfirm(false);setNonce('');}}/></label></div>
     <label className="confirm-label"><input type="checkbox" checked={confirm} onChange={e=>setConfirm(e.target.checked)} disabled={!ready||!!busy||dirty}/>J’autorise une seule tentative pour cet article, dans TEST, avec les valeurs affichées.</label>
     <div className="agent-actions"><button disabled={!ready||!!busy||dirty||!confirm||actor.trim().length<2||reason.trim().length<8||operation.status!=='prepared'} onClick={()=>run('Enregistrement de l’approbation…',async()=>{const value=await api(path+'/approve',{method:'POST',body:JSON.stringify({revision:session.revision,approval:{digest:operation.digest,confirm:true,actor,reason}})});setSession(await api(path));setNonce(value.approval_token);})}>Approuver cette création</button>
     <button disabled={!ready||!!busy||dirty||!nonce||!confirm} onClick={()=>run('Tentative unique et relectures…',async()=>{const oneShot=nonce;setNonce('');accept(await api(path+'/execute',{method:'POST',body:JSON.stringify({revision:session.revision,execution:{operation_id:operation.id,approval_token:oneShot}})}));})}>Exécuter la création approuvée</button></div>
     {!ready&&<p className="hint">Exécution désactivée : HTTPS, compte technique et preuves de droits doivent être validés côté serveur. Une validation de brouillon ne les remplace pas.</p>}
     {operation.result&&<details open><summary>Résultat SOAP et relecture</summary><pre>{JSON.stringify({status:operation.status,result:operation.result,read:operation.after_record},null,2)}</pre></details>}
    </>}
    {Object.keys(session.outcome||{}).length>0&&<div className={session.outcome.confirmed?'message success':'message'}><strong>{session.outcome.confirmed?'Article créé et confirmé par SOAP read et SQL':'Création non confirmée — ne pas relancer automatiquement'}</strong><pre>{JSON.stringify(session.outcome,null,2)}</pre></div>}
   </div>
   <details className="panel"><summary>Historique détaillé de cette demande</summary>{session.history.map((event,i)=><div className="agent-event" key={i}><strong>{event.kind}</strong> · {new Date(event.created_at).toLocaleString('fr-FR')}<pre>{JSON.stringify(event.payload,null,2)}</pre></div>)}</details>
  </>}
  <div className="panel"><h2>Historique des demandes</h2><button disabled={!token||!!busy} onClick={()=>run('Chargement de l’historique…',loadHistory)}>Charger l’historique</button>
   <ul className="agent-history">{history.map(item=><li key={item.id}><button disabled={!!busy} onClick={()=>run('Ouverture de la demande…',async()=>accept(await api('conversations/'+item.id)))}>{item.draft.code_article||'Code à compléter'} — {item.draft.designation||item.message}</button><span>{item.outcome?.confirmed?'Confirmé Sage + SQL':item.validated?'Brouillon validé':'À compléter'} · {new Date(item.created_at).toLocaleString('fr-FR')}</span></li>)}</ul>
  </div>
 </section>;
}
