import React,{useState} from 'react';
import {LogIn,UserPlus,ShieldCheck,LoaderCircle,HardDrive} from 'lucide-react';

export function AuthScreen({onAuthenticated}){
 const [mode,setMode]=useState('login'),[name,setName]=useState(''),[email,setEmail]=useState(''),[password,setPassword]=useState(''),[confirmation,setConfirmation]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function submit(e){e.preventDefault();setError('');if(mode==='register'&&password!==confirmation){setError('Les mots de passe ne correspondent pas.');return;}setBusy(true);try{
  const response=await fetch('/api/v1/chat/auth/'+mode,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({email,password,...(mode==='register'?{display_name:name}:{})})});
  const body=await response.json();if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:'Vérifiez les informations saisies.');setPassword('');setConfirmation('');onAuthenticated(body);
 }catch(e){setError(e.message);}finally{setBusy(false);}}
 return <main className="auth-screen"><section className="auth-intro"><div className="chat-logo">SAGE <span>Agent IA</span></div><span className="chat-mode">Environnement TEST</span><h1>Votre assistant Sage X3,<br/>votre espace de travail.</h1><p>Préparez vos articles et fournisseurs, retrouvez vos conversations et gardez la main sur chaque création.</p><div className="auth-promise"><ShieldCheck size={24}/><span>Vos fiches restent des brouillons jusqu’à votre confirmation.</span></div></section><section className="auth-card"><div className="auth-icon">{mode==='login'?<LogIn/>:<UserPlus/>}</div><h2>{mode==='login'?'Bienvenue':'Créer votre compte'}</h2><p>{mode==='login'?'Connectez-vous pour retrouver votre historique.':'Un espace personnel de 200 Mo pour vos conversations et fichiers.'}</p><form onSubmit={submit}>
 {mode==='register'&&<label>Nom complet<input autoComplete="name" value={name} onChange={e=>setName(e.target.value)} minLength={2} maxLength={80} required/></label>}
 <label>Adresse e-mail<input type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} maxLength={254} required/></label>
 <label>Mot de passe<input type="password" autoComplete={mode==='login'?'current-password':'new-password'} value={password} onChange={e=>setPassword(e.target.value)} minLength={mode==='register'?12:1} maxLength={128} required/></label>
 {mode==='register'&&<><small>12 caractères minimum. Utilisez une phrase difficile à deviner.</small><label>Confirmer le mot de passe<input type="password" autoComplete="new-password" value={confirmation} onChange={e=>setConfirmation(e.target.value)} maxLength={128} required/></label></>}
 {error&&<p className="chat-error" role="alert">{error}</p>}<button className="primary" type="submit" disabled={busy}>{busy?<LoaderCircle className="spin" size={18}/>:mode==='login'?<LogIn size={18}/>:<UserPlus size={18}/>} {mode==='login'?'Se connecter':'Créer mon compte'}</button>
 </form><p className="auth-switch">{mode==='login'?'Pas encore de compte ?':'Déjà inscrit ?'} <button disabled={busy} onClick={()=>{setMode(mode==='login'?'register':'login');setPassword('');setConfirmation('');setError('');}}>{mode==='login'?'S’inscrire':'Se connecter'}</button></p></section></main>;
}

export function StorageMeter({storage}){
 if(!storage)return null;
 const used=storage.used_bytes/1048576,limit=storage.limit_bytes/1048576;
 return <section className={'storage-meter '+(storage.full?'is-full':storage.warning?'is-warning':'')} aria-label="Espace de stockage"><div><HardDrive size={16}/><strong>Espace personnel</strong><span>{used.toLocaleString('fr-FR',{maximumFractionDigits:1})} / {limit.toLocaleString('fr-FR',{maximumFractionDigits:1})} Mo</span></div><progress aria-label="Stockage utilisé" value={Math.min(storage.used_bytes,storage.limit_bytes)} max={storage.limit_bytes}/>{storage.full?<p role="alert">Espace plein. Supprimez des conversations ou fichiers pour continuer.</p>:storage.warning?<p role="status">Plus de 80 % utilisés. Pensez à libérer de l’espace.</p>:<small>Conversations, fichiers, brouillons et mémoire.</small>}</section>;
}
