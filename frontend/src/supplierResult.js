const requiredComparisons=['Nom','NomCourt','ICE','IF','RC','Adresse','Ville','Telephone','Fax','Paiement','Categorie','CodeComptable','RegimeTaxe','Devise','TypeMontant','Pays','DateRegularite'];
export function supplierResult(operation){
 if(!operation?.result)return null;
 const proof=operation.result.supplier_verification;
 const comparisons=proof?.comparisons||{};
 const addressVerified=['Adresse2','Adresse3'].every(key=>operation.parameters?.[key]===undefined||comparisons[key]===true);
 if(operation.transport==='direct_sql'){
  const confirmed=operation.resource==='suppliers'&&operation.action==='create'&&operation.status==='succeeded'&&operation.result.status===1&&operation.after_record?.exists===true&&proof?.confirmed===true&&['TEST','OB'].includes(operation.folder)&&proof.folder===operation.folder&&proof.code===operation.record_keys?.BPSNUM&&proof.record?.BPSNUM_0===proof.code&&proof.sql_readback?.source==='SQL '+operation.folder&&proof.sql_readback?.folder===operation.folder&&proof.sql_readback?.ok===true&&proof.sql_readback?.rows?.length===1&&requiredComparisons.every(key=>comparisons[key]===true)&&Object.values(comparisons).every(x=>x===true)&&proof.errors?.length===0;
  return {confirmed:confirmed&&addressVerified,label:confirmed&&addressVerified?'Fournisseur créé avec succès':'Création à vérifier',code:proof?.code||operation.record_keys?.BPSNUM,record:confirmed&&addressVerified?proof.record:null,message:confirmed&&addressVerified?'Nous vous informons que le fournisseur a été créé. Ses informations ont été vérifiées dans '+operation.folder+'.':'La création n’est pas encore confirmée. Vérifiez la fiche avant de réessayer.'};
 }
 const confirmed=operation.resource==='suppliers'&&operation.action==='create'&&operation.status==='succeeded'&&operation.result.status===1&&operation.after_record?.exists===true&&proof?.confirmed===true&&proof.created_and_active===true&&proof.folder==='TEST'&&proof.active===true&&proof.code===operation.record_keys?.BPSNUM&&proof.record?.BPSNUM_0===proof.code&&proof.record?.supplier_active===2&&proof.record?.partner_active===2&&proof.sql_readback?.source==='SQL TEST'&&proof.sql_readback?.folder==='TEST'&&proof.sql_readback?.ok===true&&proof.sql_readback?.rows?.length===1&&Object.keys(comparisons).length>=8&&Object.values(comparisons).every(x=>x===true)&&proof.errors?.length===0;
 return {confirmed,label:confirmed?'Fournisseur créé et activé avec succès':'Vérification fournisseur incomplète — ne pas relancer',
   code:proof?.code||operation.record_keys?.BPSNUM,record:confirmed?proof.record:null,
   message:confirmed?'La fiche a été vérifiée par SOAP read et SQL dans TEST. Consultation : GESBPS.':'Consultez les messages Sage, le statut fournisseur et les différences. Aucune nouvelle tentative automatique.'};
}
