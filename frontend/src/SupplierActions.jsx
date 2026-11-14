import React,{useState,useEffect} from 'react';
export function SupplierActions({partner,security,busy,onAction}){
 const op=partner.operation;
 const [duplicatesConfirmed,setDuplicatesConfirmed]=useState(false);
 const [draftOnlyConfirmed,setDraftOnlyConfirmed]=useState(false);
 useEffect(()=>setDraftOnlyConfirmed(false),[op?.id,partner.forme_juridique]);
 useEffect(()=>setDuplicatesConfirmed(false),[op?.id]);
 const warnings=op?.duplicate_warnings||[];
 if(!security?.ready)return <p role="status">{security?.blockers?.join(' ')||'La création est momentanément indisponible. Vos informations sont conservées.'}</p>;
 if(['executing','ambiguous','unverified','succeeded','failed'].includes(op?.status))return null;
 return <section aria-label="Enregistrement fournisseur">
 {(!op||['invalidated','blocked'].includes(op.status))&&<button disabled={busy||!onAction||!partner.nom} onClick={()=>onAction(partner,'prepare')}>Préparer l’enregistrement fournisseur</button>}
 {op?.status==='blocked'&&<p role="status">{op.validation?.message||'Certaines informations doivent être vérifiées. La fiche n’a pas été créée.'}</p>}
 {op?.status==='blocked'&&<button disabled>Confirmer la création</button>}
 {warnings.length>0&&op?.status!=='blocked'&&<p role="alert">Nous vous informons que ces informations sont déjà utilisées par un autre fournisseur : {warnings.map(w=>w.code+' — '+(w.name||'Nom non renseigné')).join(', ')}. La création est bloquée.</p>}
 {op?.draft_only_fields?.length>0&&op?.status==='prepared'&&<label className="draft-notice"><input type="checkbox" checked={draftOnlyConfirmed} onChange={e=>setDraftOnlyConfirmed(e.target.checked)}/>Je confirme que la forme juridique « {partner.forme_juridique} » restera uniquement dans le brouillon, sans être enregistrée dans Sage.</label>}
 {op?.status==='prepared'&&!warnings.length&&<button disabled={busy||!onAction||!!op.draft_only_fields?.length&&!draftOnlyConfirmed} onClick={()=>onAction(partner,'approve',{confirm_draft_only_fields:draftOnlyConfirmed})}>{partner.dossier_cible==='OB'?'Confirmer la création dans Production OB':'Confirmer la création'}</button>}
 {op?.status==='approved'&&!warnings.length&&<button disabled={busy||!onAction} onClick={()=>onAction(partner,'execute')}>{partner.dossier_cible==='OB'?'Confirmer la création dans Production OB':'Confirmer la création'}</button>}
 </section>;
}
