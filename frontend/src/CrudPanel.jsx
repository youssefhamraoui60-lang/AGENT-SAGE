import React,{useState,useEffect} from 'react';
import {SupplierResult} from './SupplierResult.jsx';
const names={articles:'Articles',suppliers:'Fournisseurs','article-sites':'Articles-Sites'};
const keyNames={articles:['ITMREF'],suppliers:['BPSNUM'],'article-sites':['ITMREF','STOFCY']};
export default function CrudPanel({resource,token,request}){
 const [schema,setSchema]=useState(null),[keys,setKeys]=useState(()=>{const url=new URLSearchParams(location.search);return Object.fromEntries(keyNames[resource].map(k=>[k,url.get('resource')===resource?(url.get(k==='STOFCY'?'site':'code')||''):'' ]));}),[fields,setFields]=useState([]),[action,setAction]=useState('create');
 const [records,setRecords]=useState(null),[record,setRecord]=useState(null),[operation,setOperation]=useState(null),[history,setHistory]=useState([]),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [actor,setActor]=useState(''),[reason,setReason]=useState(''),[confirm,setConfirm]=useState(false),[approvalToken,setApprovalToken]=useState('');
 useEffect(()=>{setApprovalToken('');setConfirm(false);setOperation(null);setRecord(null);setRecords(null);setHistory([]);},[token]);
 async function run(fn){setBusy(true);setError('');try{await fn();}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function getSchema(){const value=await request(resource+'/schema');setSchema(value);return value;}
 async function refreshHistory(){setHistory((await request(resource+'/history')).operations);}
 const suffix=Object.values(keys).map(encodeURIComponent).join('/');
 async function consult(){const data=await request(resource+'/'+suffix);setRecord(data.record||data);}
 async function prepare(){
  const changes=fields.map(row=>{const meta=schema.fields.find(f=>f.group+'.'+f.name===row.path);return {group:meta.group,name:meta.name,value:meta.dimension>1?JSON.parse(row.value):row.value,...(meta.table?{row:Number(row.row)}:{})};});
  setApprovalToken('');setConfirm(false);setOperation(await request(resource+'/prepare',{method:'POST',body:JSON.stringify({action,keys,fields:changes})}));await refreshHistory();
 }
 async function approve(){const result=await request('operations/'+operation.id+'/approve',{method:'POST',body:JSON.stringify({digest:operation.digest,confirm:true,actor,reason})});setApprovalToken(result.approval_token);setOperation(await request('operations/'+operation.id));await refreshHistory();}
 async function execute(){
  const nonce=approvalToken;setApprovalToken('');
  const tail=operation.action==='update'?'/'+keyNames[resource].map(k=>encodeURIComponent(operation.record_keys[k])).join('/'):'';
  const result=await request(resource+tail,{method:operation.action==='update'?'PATCH':'POST',body:JSON.stringify({operation_id:operation.id,approval_token:nonce})});
  setApprovalToken('');setOperation(result);setRecord(result.after_record);await refreshHistory();
 }
 function addField(){const meta=schema.fields.find(f=>action==='create'||f.update_allowed);if(meta)setFields([...fields,{path:meta.group+'.'+meta.name,value:meta.dimension>1?JSON.stringify(Array(meta.dimension).fill('')):'',row:1}]);}
 function updateField(index,patch){setFields(fields.map((v,i)=>i===index?{...v,...patch}:v));setOperation(null);setApprovalToken('');}
 return <section className="panel crud-panel" data-testid={'crud-'+resource}>
  <h2>{names[resource]} · opérations contrôlées dans TEST</h2>
  <p>Consulter, préparer et examiner chaque opération. L’exécution reste verrouillée tant que la sécurité et l’approbation individuelle ne sont pas validées.</p>
  <div className="controls"><button disabled={!token||busy} onClick={()=>run(getSchema)}>Consulter la publication</button><button disabled={!token||busy} onClick={()=>run(async()=>setRecords((await request(resource+'?limit=10')).records))}>Lister 10 fiches</button><button disabled={!token||busy} onClick={()=>run(refreshHistory)}>Actualiser l’historique</button></div>
  {schema&&<><p className="hint">{schema.publication} · {schema.object} · {schema.sage_menu}</p><p className="message">{schema.security.ready?'Conditions techniques attestées; approbation individuelle encore requise.':'Écritures verrouillées : '+schema.security.blockers.join(', ')}</p></>}
  <div className="draft-grid key-grid">{keyNames[resource].map(k=><label key={k}>{k==='STOFCY'?'Code site':k==='BPSNUM'?'Code fournisseur':'Code article'}<input aria-label={'Clé '+k} value={keys[k]} maxLength={k==='STOFCY'?5:k==='BPSNUM'?15:20} onChange={e=>{setKeys({...keys,[k]:e.target.value});setOperation(null);setRecord(null);setApprovalToken('');}}/></label>)}</div>
  <button disabled={!token||busy||Object.values(keys).some(v=>!v)} onClick={()=>run(consult)}>Rechercher et lire la fiche</button>
  {records&&<div className="scroll"><table><thead><tr>{Object.keys(records[0]||{}).map(k=><th key={k}>{k}</th>)}</tr></thead><tbody>{records.map((row,i)=><tr key={i} onClick={()=>{const next={};for(const k of keyNames[resource])next[k]=row[k]||'';setKeys(next);setRecord(null);setOperation(null);setApprovalToken('');}}>{Object.values(row).map((v,j)=><td key={j}>{String(v)}</td>)}</tr>)}</tbody></table>{!records.length&&<p>Aucune fiche retournée.</p>}</div>}
  {record&&<details open><summary>Fiche relue / résultat SOAP</summary><pre className="xml-preview">{JSON.stringify(record,null,2)}</pre></details>}
  {schema&&<><h3>Préparation</h3><label>Type d’opération<select aria-label="Type d’opération" value={action} onChange={e=>{setAction(e.target.value);setFields([]);setOperation(null);setApprovalToken('');}}><option value="create">Création</option><option value="update">Modification</option></select></label>
   <p className="hint">Les valeurs autorisées et les champs conditionnels doivent être examinés. Une modification ne peut porter que sur les champs explicitement autorisés.</p>
   {fields.map((row,i)=>{const meta=schema.fields.find(f=>f.group+'.'+f.name===row.path);return <div className="crud-field" key={i}><label>Champ publié<select aria-label={'Champ '+i} value={row.path} onChange={e=>{const next=schema.fields.find(f=>f.group+'.'+f.name===e.target.value);updateField(i,{path:e.target.value,value:next.dimension>1?JSON.stringify(Array(next.dimension).fill('')):'',row:1});}}>{schema.fields.filter(f=>action==='create'||f.update_allowed).map(f=><option key={f.group+'.'+f.name} value={f.group+'.'+f.name}>{f.group}.{f.name} — {f.label}</option>)}</select></label>
    <label>{meta?.dimension>1?'Valeurs du tableau JSON ('+meta.dimension+' positions)':'Valeur'}<textarea aria-label={'Valeur '+i} value={row.value} onChange={e=>updateField(i,{value:e.target.value})}/></label>
    {meta?.table&&<label>Ligne du tableau<input type="number" min="1" value={row.row} onChange={e=>updateField(i,{row:e.target.value})}/></label>}
    {meta?.menu?.length>0&&<p className="hint">{meta.menu.map(v=>v.value+' = '+v.label).join(' · ')}</p>}
    <button onClick={()=>{setFields(fields.filter((_,n)=>n!==i));setOperation(null);setApprovalToken('');}}>Retirer ce champ</button></div>;})}
   <div className="controls"><button disabled={busy} onClick={addField}>Ajouter un champ</button><button disabled={busy||!fields.length||Object.values(keys).some(v=>!v)} onClick={()=>run(prepare)}>Préparer l’opération sans écrire</button></div>
  </>}
  {error&&<p role="alert" className="message">{error}</p>}
  {operation&&<div className="operation-review"><h3>Opération {operation.action==='create'?'de création':'de modification'} · {operation.status}</h3><p>Identifiant : {operation.id}</p><p className="hint">Empreinte : {operation.digest}</p>
   <h4>Avant</h4><pre className="xml-preview">{JSON.stringify(operation.before_record,null,2)}</pre><h4>Changements proposés</h4><pre className="xml-preview">{JSON.stringify(operation.checks.after_proposed,null,2)}</pre><h4>XML SOAP préparé</h4><pre className="xml-preview">{operation.object_xml}</pre>
   <p className="message">{[...operation.checks.blockers,...operation.security.blockers].join(', ')||'Revue humaine spécifique nécessaire.'}</p>
   <div className="draft-grid"><label>Opérateur approbateur<input value={actor} onChange={e=>setActor(e.target.value)}/></label><label>Motif de l’approbation<input value={reason} onChange={e=>setReason(e.target.value)}/></label></div>
   <label className="confirm-label"><input type="checkbox" checked={confirm} onChange={e=>setConfirm(e.target.checked)}/>J’approuve uniquement cette opération, ces clés et ces valeurs dans TEST.</label>
   <div className="controls"><button disabled={busy||!operation.security.ready||operation.status!=='prepared'||!confirm||actor.length<2||reason.length<8} onClick={()=>run(approve)}>Enregistrer l’approbation spécifique</button><button disabled={busy||!operation.security.ready||operation.status!=='approved'||!approvalToken} onClick={()=>run(execute)}>Exécuter une seule fois via FastAPI</button><button disabled={busy} onClick={()=>run(async()=>setRecord((await request('operations/'+operation.id+'/reconcile',{method:'POST'})).read))}>Relire uniquement, sans réessayer</button></div>
   {resource==='suppliers'&&<SupplierResult operation={operation}/>}
   {operation.result&&<pre className="xml-preview">{JSON.stringify({result:operation.result,after:operation.after_record},null,2)}</pre>}
   <h4>Historique de cette opération</h4><pre className="xml-preview">{JSON.stringify(operation.history,null,2)}</pre>
  </div>}
  {history.length>0&&<><h3>Historique récent</h3><div className="scroll"><table><thead><tr><th>Type</th><th>Clés</th><th>État</th><th>Détail</th></tr></thead><tbody>{history.map(row=><tr key={row.id}><td>{row.action}</td><td>{JSON.stringify(row.record_keys)}</td><td>{row.status}</td><td><button onClick={()=>run(async()=>{setApprovalToken('');setOperation(await request('operations/'+row.id));})}>Examiner</button></td></tr>)}</tbody></table></div></>}
 </section>;
}
