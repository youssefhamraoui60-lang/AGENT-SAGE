import React,{useState} from 'react';
import {CompactTable} from './CompactTable.jsx';
import {SupplierTurnTable} from './SupplierTurnTable.jsx';
import {SupplierCard} from './SupplierCard.jsx';
import {SupplierPanel} from './SupplierPanel.jsx';
import {SupplierActions} from './SupplierActions.jsx';
import {Article} from './ArticleCards.jsx';
import {ModificationCard} from './ModificationCard.jsx';
import {CategorySqlCard} from './ArticleSqlCards.jsx';
import {sqlConfirmed} from './ArticleSqlCards.jsx';
import {creationResult} from './creationResult.js';
import {confirmationItems,supplierSnapshot,terminal} from './chatPresentation.js';

export function SupplierSnapshots({snapshots,payments,historical=false}){
 const [open,setOpen]=useState(false);
 if(!snapshots?.length)return null;
 if(historical)return <details className="supplier-snapshot-history" onToggle={e=>setOpen(e.currentTarget.open)}><summary>Anciennes informations · {snapshots.length} fiche{snapshots.length>1?'s':''}</summary>{open&&<SupplierSnapshots snapshots={snapshots} payments={payments}/>}</details>;
 if(snapshots.length===1)return <SupplierTurnTable snapshot={snapshots[0]} payments={payments}/>;
 const cell=(s,key)=>s.rows.find(r=>r.key===key)?.value||'Non renseigné';
 return <section className="supplier-group-table"><CompactTable label="Résumé des fournisseurs" columns={['Fournisseur','Ville','Forme juridique','État']} rows={snapshots.map(s=>[s.name||'Nom à préciser',cell(s,'Ville'),cell(s,'FormeJuridique'),['prepared','approved'].includes(s.stage)?'À confirmer':s.stage==='blocked'?'À vérifier':'Brouillon'])}/><details><summary>Informations de chaque fournisseur</summary>{snapshots.map(s=><details key={s.supplier_id}><summary>{s.name||'Fournisseur à compléter'}</summary><SupplierTurnTable snapshot={s} payments={payments}/></details>)}</details></section>;
}

export function ArticleSummaries({articles}){
 if(!articles?.length)return null;
 return <CompactTable label="Résumé des articles" columns={['Code','Désignation','Catégorie','Site','État']} rows={articles.map(a=>[a.code_article||'À préciser',a.designation||'À préciser',a.categorie||'À préciser',a.requested_sites?.join(', ')||a.site||'À préciser',sqlConfirmed(a)||creationResult(a)?.confirmed?'Créé':['prepared','approved'].includes(a.operation?.status)?'À confirmer':terminal(a.operation)?'À vérifier':'Brouillon'])}/>;
}

function ArticleDetails({article,number,session,busy,onAction}){
 const [open,setOpen]=useState(false);
 return <details onToggle={event=>setOpen(event.currentTarget.open)}><summary>{article.designation||article.code_article||'Article à compléter'}</summary>{open&&<Article article={article} number={number} session={session} busy={busy} onAction={onAction}/>}</details>;
}

export function DraftTools({session,busy,api,onUpdate,supplierAction,articleAction,modificationAction,categoryAction,payments}){
 if(!session)return null;
 const locked=busy||session.supplier_security?.blockers?.some(x=>x.includes('Pilote MCP'));
 const s=session.state,items=confirmationItems(session),pending=new Set(items.map(i=>i.kind+':'+i.id));
 const suppliers=(s.active_supplier_task||'create')==='create'?(s.partners||[]).filter(p=>p.kind==='supplier'&&!pending.has('supplier:'+p.id)&&!terminal(p.operation)):[];
 const customers=(s.partners||[]).filter(p=>p.kind==='customer');
 const articles=(s.articles||[]).filter(a=>!pending.has('article:'+a.id));
 const modifications=(s.modification_drafts||[]).filter(d=>!pending.has('modification:'+d.id)&&!['cancelled','succeeded'].includes(d.operation?.status)&&(!s.supplier_tasks||d.resource!=='supplier'||s.active_supplier_task==='modify'));
 const categories=(s.category_drafts||[]).filter(d=>!pending.has('category:'+d.id)&&!terminal(d.operation));
 const control=s.active_supplier_task==='control'?s.supplier_tasks?.control:null;
 if(!suppliers.length&&!customers.length&&!articles.length&&!modifications.length&&!categories.length&&!control)return null;
 return <details className="inline-draft-tools"><summary>Consulter ou compléter les fiches</summary>
 {control&&<section aria-label="Contrôle fournisseur"><strong>{control.code}</strong><p>{control.message}</p></section>}
 {customers.map(p=><details key={p.id}><summary>Client · {p.nom||'À compléter'}</summary><CompactTable label="Informations du client" columns={['Information','Valeur']} rows={[["Nom",p.nom||'Non renseigné'],['Ville',p.ville||'Non renseignée'],['Adresse',p.adresse||'Non renseignée']]}/><p>Informations conservées. Aucune création client disponible.</p></details>)}
 {suppliers.map(p=><details key={p.id}><summary>{p.nom||'Fournisseur à compléter'} · {p.operation?.status==='blocked'?'À vérifier':'Brouillon'}</summary><SupplierPanel partner={p} session={session} busy={locked} api={api} onUpdate={onUpdate} onAction={supplierAction} payments={payments} hideConfirmation/></details>)}
 {articles.map((a,i)=><ArticleDetails key={a.id} article={a} number={i+1} session={session} busy={locked} onAction={articleAction}/>)}
 {modifications.map(d=><details key={d.id}><summary>Modification · {d.code}</summary><ModificationCard draft={d} busy={locked} onAction={modificationAction}/></details>)}
 {categories.map(d=><details key={d.id}><summary>Catégorie · {d.code}</summary><CategorySqlCard draft={d} busy={locked} onAction={categoryAction}/></details>)}
 </details>;
}

export function ConfirmationCards({items,session,busy,api,onUpdate,supplierAction,articleAction,modificationAction,categoryAction,payments}){
 return <>{items.map(item=>{
  const r=item.record;
  if(item.kind==='supplier')return <SupplierConfirmation key={'supplier:'+r.id} partner={r} session={session} busy={busy} api={api} onUpdate={onUpdate} onAction={supplierAction} payments={payments}/>;
  if(item.kind==='modification')return <div className="confirmation-card" key={'modification:'+r.id}><span className="confirmation-kind">{r.changes?.deactivate?'Désactiver':r.changes?.activate?'Activer':'Modifier une fiche'}</span><ModificationCard compact draft={r} busy={busy} onAction={modificationAction} readonly={session.supplier_security?.blockers?.some(b=>b.includes('Pilote MCP'))}/></div>;
  if(item.kind==='category')return <div className="confirmation-card" key={'category:'+r.id}><span className="confirmation-kind">Créer une catégorie</span><CategorySqlCard draft={r} busy={busy} onAction={categoryAction}/></div>;
  return <div className="confirmation-card" key={'article:'+r.id}><span className="confirmation-kind">Confirmer l’article ou son site</span><Article compact article={r} number={1} session={session} busy={busy} onAction={articleAction}/></div>;
 })}</>;
}

function SupplierConfirmation({partner:r,session,busy,api,onUpdate,onAction,payments}){
 const [editing,setEditing]=useState(false);
 return <section className="confirmation-card" aria-label={'Confirmation fournisseur '+r.nom}><span className="confirmation-kind">Créer un fournisseur</span><h3>{r.nom}</h3><p className="confirmation-summary">{r.ville||r.operation?.parameters?.Ville||'Ville non renseignée'}{r.forme_juridique?' · '+r.forme_juridique:''}</p><details><summary>Données exactes à confirmer</summary><SupplierTurnTable snapshot={supplierSnapshot(r)} payments={payments}/><details><summary>Tous les paramètres et sources</summary><SupplierCard hideActions partner={r} security={session.supplier_security} busy={busy}/></details></details><details><summary>Modifier la fiche</summary><SupplierPanel partner={r} session={session} busy={busy} api={api} onUpdate={onUpdate} onAction={onAction} payments={payments} hideConfirmation onEditingChange={setEditing}/></details>{editing&&<p role="status">Enregistrez ou annulez vos corrections avant de confirmer.</p>}<SupplierActions partner={r} security={session.supplier_security} busy={busy||editing} onAction={onAction}/></section>;
}
