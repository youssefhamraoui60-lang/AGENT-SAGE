import React,{useEffect,useState} from 'react';
export function AiControls({api,session,busy,onMode,owner}){
 const [status,setStatus]=useState(null),[error,setError]=useState('');
 const last=session?.state?.ai_calls?.at(-1),local=session?.state?.ai_mode==='local';
 useEffect(()=>{let active=true;api('ai/status').then(r=>{if(active){setStatus(r);setError('');}}).catch(()=>{if(active)setError('Suivi IA indisponible.');});return()=>{active=false;};},[owner,session?.revision,last?.seconds]);
 return <section aria-label="Mode et utilisation IA" className="ai-controls">
  <p>{local?'Mode local : Qwen':status?.provider==='deepseek'?'IA principale : DeepSeek':'IA locale : Qwen'}{last&&<small style={{display:'block'}}>Dernière réponse : {last.provider==='deepseek'?'DeepSeek':last.fallback_reason?'Qwen · secours automatique':'Qwen local'}</small>}</p>
  <label>Mode IA <select aria-label="Mode IA" value={local?'local':'auto'} disabled={busy||Boolean(session?.state?._pending)} onChange={e=>onMode(e.target.value)}><option value="auto">Automatique — DeepSeek, secours Qwen</option><option value="local">Local uniquement — Qwen</option></select></label>
  <details><summary>Utilisation et budget IA</summary>
   {status&&<><p>Plafond partagé : {status.daily_budget_usd} USD / jour UTC.</p>{status.usage_30_days.map(r=><p key={r.provider}>{r.provider} · {r.calls} appels · {r.input_tokens} tokens entrants / {r.output_tokens} sortants · estimation {Number(r.estimated_cost_usd).toFixed(6)} USD{Number(r.pending_estimates)>0?' · coûts en attente de confirmation':''}</p>)}<small>Votre usage des 30 derniers jours. Estimation, pas une facture. Aucun entraînement automatique à partir des réponses générées.</small></>}{error&&<p>{error}</p>}
  </details>
 </section>;
}
