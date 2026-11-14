import React, {useState} from 'react';

import './style.css';
import CrudPanel from './CrudPanel';
import ArticleAgent from './ArticleAgent';

const errors={sage_credentials_not_configured:'Les identifiants SOAP ne sont pas encore configurés sur le serveur.',sage_authentication_required:'Sage a refusé l’authentification. Vérifiez le compte et ses autorisations.',sage_timeout:'Sage n’a pas répondu dans le délai prévu.',sage_business_error:'Sage a retourné une erreur métier. Vérifiez la publication et le pool côté Sage.',sage_network_error:'Le serveur Sage est indisponible.',sage_unrecognized_article_result:'Le format retourné par la publication doit être vérifié.'};
export default function LegacyApp(){
 const [resource,setResource]=useState(()=>['agent','articles','suppliers','article-sites'].includes(new URLSearchParams(location.search).get('resource'))?new URLSearchParams(location.search).get('resource'):'articles');
 const [token,setToken]=useState(()=>{try{return localStorage.getItem('agent-sage-local-token')||'';}catch{return '';}}),[limit,setLimit]=useState(20),[rows,setRows]=useState(null),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),[state,setState]=useState(null),[metadata,setMetadata]=useState(null),[reference,setReference]=useState('CPJ35'),[detail,setDetail]=useState(null);
 function rememberToken(value){setToken(value);try{if(value)localStorage.setItem('agent-sage-local-token',value);else localStorage.removeItem('agent-sage-local-token');}catch{/* Keep this tab usable when browser storage is unavailable. */}}
 const [draft,setDraft]=useState(null),[draftBusy,setDraftBusy]=useState(false),[draftError,setDraftError]=useState('');
 const [form,setForm]=useState({reference:'',designation:'',categorie:'',unite_stock:'',unite_achat:'',unite_vente:'',coefficient_achat:'',coefficient_vente:'',statut:'',gestion_stock:'',gestion_lots:'',code_comptable:''});
 async function request(path,options={}){
  const response=await fetch('/api/v1/sage/'+path,{...options,headers:{'X-Approval-Token':token,'Content-Type':'application/json'},cache:'no-store'});
  const body=await response.json();
  if(!response.ok) throw new Error(response.status===403?'Accès refusé : vérifiez le jeton ou les autorisations.':typeof body.detail==='object'&&!Array.isArray(body.detail)?'Écriture verrouillée : '+(body.detail.blockers||[body.detail.code]).join(', '):errors[body.detail]||(typeof body.detail==='string'?body.detail:'Champs invalides : vérifiez les valeurs saisies.'));
  return body;
 }
 async function load(){setBusy(true);setNotice('');setRows(null);setMetadata(null);
  try{setState(await request('status'));await request('description');const result=await request('articles?limit='+limit);setRows(result.articles);setMetadata(result);setNotice('Lecture effectuée directement dans Sage.');}
  catch(error){setNotice(error.message);}finally{setBusy(false);}
 }
 async function read(ref=reference){setReference(ref);setBusy(true);setNotice('');setDetail(null);
  try{const result=await request('articles/'+encodeURIComponent(ref));setDetail(result.article);setNotice('Article lu directement dans Sage.');}
  catch(error){setNotice(error.message);}finally{setBusy(false);}
 }
 async function prepare(event){event.preventDefault();setDraftBusy(true);setDraft(null);setDraftError('');
  try{const body=Object.fromEntries(Object.entries(form).filter(([key,value])=>value!==''));setDraft(await request('article-preparations',{method:'POST',body:JSON.stringify(body)}));}
  catch(error){setDraftError(error.message);}finally{setDraftBusy(false);}
 }
 const columns=rows?[...new Set(rows.flatMap(row=>Object.keys(row)))]:[];
 return <main><header><span className="brand">AGENT-SAGE-X3 <b>V12</b></span><span className="badge">Dossier TEST</span></header>
  <section className="intro"><p className="eyebrow">DOSSIER TEST · WEB SERVICES SOAP</p><h1>Consultation et opérations Sage X3</h1><p>Articles, fournisseurs et articles-sites. Chaque écriture exige ses propres contrôles et son approbation.</p></section>
  <nav className="resource-tabs" aria-label="Objets Sage">{[['agent','Agent IA'],['articles','Articles'],['suppliers','Fournisseurs'],['article-sites','Articles-Sites']].map(([id,label])=><button key={id} aria-pressed={resource===id} onClick={()=>setResource(id)}>{label}</button>)}</nav>
  <section className="panel"><div className="controls"><label>Jeton d’accès local<input type="password" autoComplete="off" value={token} onChange={event=>rememberToken(event.target.value)} placeholder="APPROVAL_TOKEN du projet"/></label>{resource==='articles'&&<><label>Nombre maximal<select value={limit} onChange={event=>setLimit(Number(event.target.value))}>{[10,20,50].map(n=><option key={n}>{n}</option>)}</select></label><button disabled={busy||!token} onClick={load}>{busy?'Lecture en cours…':'Charger les articles'}</button></>}</div>
   <p className="hint">Le jeton est mémorisé dans ce navigateur pour préremplir ce champ. Effacez le champ pour l’oublier. Les identifiants Sage restent côté serveur.</p>
   {resource==='articles'&&<><div className="controls detail-search"><label>Référence article<input value={reference} maxLength={20} onChange={event=>setReference(event.target.value)} /></label><button disabled={busy||!token||!reference} onClick={()=>read()}>Lire cet article</button><button disabled={busy||!token} onClick={()=>read('TSTAI2610174D94B4')}>Lire l’article testé</button></div>
   {notice&&<p role="status" aria-live="polite" className={rows===null?'message':'message success'}>{notice}</p>}
   {state&&<p className="hint">Pool {state.pool} · Publication {state.publication} · Identifiants {state.credentials_configured?'configurés':'absents'}</p>}</>}
  </section>
  {resource==='agent'?<ArticleAgent token={token}/>:<CrudPanel key={resource} resource={resource} token={token} request={request}/>}
  {resource==='articles'&&<>
  {detail&&<section className="panel"><h2>Fiche article · {detail.ITMREF}</h2><dl>{Object.entries(detail).map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value||'—'}</dd></div>)}</dl></section>}
  <section className="panel results"><div className="result-heading"><h2>Résultat de lecture</h2>{rows&&<span>{rows.length} article(s) reçu(s)</span>}</div>
   {rows===null?<div className="empty">Chargez les articles pour consulter les données du serveur Sage.</div>:rows.length===0?<div className="empty">La requête Sage a réussi et n’a retourné aucun article.</div>:<div className="scroll"><table><thead><tr>{columns.map(col=><th key={col}>{col}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{columns.map(col=><td key={col}>{row[col]??'—'}</td>)}</tr>)}</tbody></table></div>}
   {metadata?.possibly_truncated&&<p className="hint">Limite atteinte : cette liste peut être partielle. Elle ne constitue pas un export complet du catalogue.</p>}
  </section>
  <section className="panel"><h2>Préparer une création · TEST</h2><p>Ce formulaire enregistre un brouillon local et vérifie le code dans Sage. Il n’envoie aucune création.</p>
   <form onSubmit={prepare}><div className="draft-grid">{[
    ['reference','Nouveau code article',20],['designation','Désignation proposée',70],['categorie','Catégorie à vérifier',5],
    ['unite_stock','Unité de stock',3],['unite_achat','Unité d’achat',3],['unite_vente','Unité de vente',3],
    ['coefficient_achat','Coefficient achat / stock',20],['coefficient_vente','Coefficient vente / stock',20]
   ].map(([key,label,max])=><label key={key}>{label}<input required maxLength={max} value={form[key]} onChange={event=>{setForm({...form,[key]:event.target.value});setDraft(null);}} /></label>)}</div>
   <p className="hint">Paramètres complémentaires facultatifs dans le brouillon. Leur caractère obligatoire dépend des règles du dossier.</p><div className="draft-grid">{[
    ['statut','Statut article (code du menu)',1],['gestion_stock','Gestion stock (code du menu)',1],
    ['gestion_lots','Gestion lots (code du menu)',3],['code_comptable','Code comptable',10]
   ].map(([key,label,max])=><label key={key}>{label}<input maxLength={max} value={form[key]} onChange={event=>{setForm({...form,[key]:event.target.value});setDraft(null);}} /></label>)}</div>
   <button className="prepare-button" disabled={!token||draftBusy}>{draftBusy?'Préparation en cours…':'Préparer le XML sans créer'}</button></form>
   {draftError&&<p role="alert" className="message">{draftError}</p>}
   {draft&&<div aria-live="polite"><h3>{draft.status==='blocked_existing'?'Code déjà existant — création bloquée':draft.status==='blocked_unknown'?'Existence non vérifiée — création bloquée':'Brouillon enregistré — revue humaine requise'}</h3><p>Référence du brouillon : {draft.id}</p><pre className="xml-preview">{draft.object_xml}</pre><p className="hint">Empreinte SHA-256 : {draft.object_sha256}</p><p>Les droits de création, valeurs autorisées et champs conditionnels restent à vérifier. Une approbation humaine explicite sera obligatoire avant toute écriture. Aucun envoi SOAP n’est disponible dans ce formulaire.</p></div>}
  </section></>}<footer>Écritures verrouillées par défaut · Contrôles de sécurité et approbation individuelle obligatoires</footer></main>;
}

