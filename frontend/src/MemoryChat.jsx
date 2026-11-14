import React,{useState} from 'react';
import {ThumbsUp,ThumbsDown} from 'lucide-react';
export function MemoryRules({message,api,conversation,onUpdate}){
 const [editing,setEditing]=useState(null),[content,setContent]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function act(item,action){setBusy(true);setError('');try{const result=await api('learning/conversations/'+conversation+'/items/'+item.id+'/action',{method:'POST',body:JSON.stringify({action,content,sha:item.sha256,confirm:action!=='edit'})});onUpdate(result);setEditing(null);}catch(e){setError(e.message);}finally{setBusy(false);}}
 return <>{message.memory_rules?.map((item,index)=><section className="chat-next-question" key={item.id} aria-label="Règle de mémoire"><strong>{index+1}. {item.status==='pending'?'Proposition à mémoriser':item.status==='validated'?'Règle mémorisée':item.status==='rejected'?'Proposition refusée':'Règle non utilisée'}</strong><p>{item.content}</p>
 {item.status==='pending'&&<><button disabled={busy} onClick={()=>act(item,'validate')}>Valider cette règle</button><button disabled={busy} onClick={()=>{setEditing(item.id);setContent(item.content);}}>Modifier cette règle</button><button disabled={busy} onClick={()=>act(item,'reject')}>Refuser cette règle</button></>}
 {editing===item.id&&['pending','validated'].includes(item.status)&&<div><label>Règle modifiée<textarea aria-label="Règle modifiée" value={content} maxLength={20000} onChange={e=>setContent(e.target.value)}/></label><button disabled={busy||!content.trim()} onClick={()=>act(item,'edit')}>Proposer la modification</button></div>}
 {item.status==='validated'&&<><button disabled={busy} onClick={()=>{setEditing(item.id);setContent(item.content);}}>Modifier cette règle</button><button disabled={busy} onClick={()=>act(item,'forget')}>Oublier cette règle</button></>}
 </section>)}{error&&<p role="alert">{error}</p>}</>;
}
export function AnswerFeedback({message,api,conversation,onUpdate,compact=false}){
 const [editing,setEditing]=useState(false),[expected,setExpected]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 if(!Number.isInteger(message.id)||message.payload?.memory_dialogue)return null;
 async function submit(verdict){setBusy(true);try{const result=await api('learning/conversations/'+conversation+'/feedback',{method:'POST',body:JSON.stringify({message_id:message.id,verdict,expected})});onUpdate(result);setEditing(false);}catch(e){setNotice(e.message);}finally{setBusy(false);}}
 return <div className="chat-muted" aria-label="Votre avis sur cette réponse"><button aria-label="Réponse correcte" disabled={busy} onClick={()=>submit('correct')}>{compact?<ThumbsUp size={16}/>:'Réponse correcte'}</button><button aria-label="À corriger" disabled={busy} onClick={()=>setEditing(!editing)}>{compact?<ThumbsDown size={16}/>:'À corriger'}</button>{editing&&<div><label>Correction attendue<textarea aria-label="Correction attendue" value={expected} maxLength={20000} onChange={e=>setExpected(e.target.value)}/></label><button disabled={busy||!expected.trim()} onClick={()=>submit('incorrect')}>Proposer ma correction</button></div>}{notice&&<p role="status">{notice}</p>}</div>;
}
export function LearningSources({context}){
 if(!context)return null;
 return <details className="chat-next-question"><summary>Sources consultées pour cette réponse</summary>
 {context.used_correction_source&&<p>Correction mémorisée réutilisée.</p>}
 {[...(context.memory||[]),...(context.documents||[])].map((item,i)=><div key={String(item.id||i)}><strong>{item.title||item.source}</strong><p>{item.content}</p><small>Source : {item.source} · {item.status==='validated'?'Validé':'À valider'}</small></div>)}
 <p>Les sources et la mémoire n’autorisent jamais une écriture dans Sage.</p></details>;
}
