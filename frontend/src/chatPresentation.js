const ready=op=>['prepared','approved'].includes(op?.status);
export const terminal=op=>['succeeded','failed','ambiguous','unverified','cancelled'].includes(op?.status);

// Presentation reads backend states; it never prepares or authorizes an operation.
export function confirmationItems(session){
 if(!session||session.state?.workflow==='cancelled')return [];
 const s=session.state||{},items=[],readonly=session.supplier_security?.blockers?.some(x=>x.includes('Pilote MCP'));
 if(readonly)return items;
 for(const p of s.partners||[])if(p.kind==='supplier'&&ready(p.operation)&&!p.operation.duplicate_warnings?.length&&session.supplier_security?.ready&&!s.supplier_creation_hold&&(s.active_supplier_task||'create')==='create')items.push({kind:'supplier',id:p.id,record:p});
 for(const d of s.modification_drafts||[])if(ready(d.operation)&&(!s.supplier_tasks||d.resource!=='supplier'||s.active_supplier_task==='modify'&&(d.code===s.supplier_tasks.control?.code||Object.hasOwn(d.changes||{},'enabled')&&s.supplier_status_batch?.codes?.includes(d.code))))items.push({kind:'modification',id:d.id,record:d});
 for(const d of s.category_drafts||[])if(ready(d.operation))items.push({kind:'category',id:d.id,record:d});
 for(const a of s.articles||[]){
  const security=a.execution?.security||session.security;
  const child=Object.values(a.strict_site_operations||{}).some(ready)||ready(a.site_request);
  if(ready(a.operation)&&security?.ready||child&&(a.execution?.site_security?.ready||security?.ready))items.push({kind:'article',id:a.id,record:a});
 }
 return items;
}

export function supplierSnapshot(p){
 const fields=[['Statut','Statut fournisseur','statut'],['Nom','Nom du fournisseur','nom'],['Ville','Ville','ville'],['FormeJuridique','Forme juridique','forme_juridique'],['ICE','ICE','ice'],['Paiement','Paiement','conditions_paiement'],['Adresse','Adresse','adresse'],['Telephone','Téléphone','telephone'],['IF','Identifiant fiscal','identifiant_fiscal'],['RC','Registre de commerce','rc'],['Pays','Pays','pays'],['Devise','Devise','devise'],['Capital','Capital','capital']];
 const parameters=p.operation?.status==='invalidated'?{}:p.operation?.parameters||{};
 return {supplier_id:p.id,name:p.nom,stage:p.operation?.status,rows:fields.flatMap(([key,label,field])=>{
  if(key==='Adresse'&&(parameters.Adresse2||parameters.Adresse3))return ['Adresse','Adresse2','Adresse3'].filter(k=>parameters[k]).map((k,i)=>({key:k,label:`Adresse — ligne ${i+1}`,value:parameters[k],origin:p.adresse?'declared':'default'}));
  const value=p[field]??parameters[key];return [{key,label,value,origin:value?'declared':'missing'}];
 })};
}

export function shortMessage(message,session){
 if(message.role==='user')return message.content;
 const id=message.payload?.modification_result,d=session?.state?.modification_drafts?.find(x=>x.id===id);
 if(d?.operation?.status==='succeeded'&&message.payload.verified===true)return `Modification confirmée pour ${d.code} dans ${d.folder==='OB'?'Production OB':'TEST'}.`;
 return message.content;
}
