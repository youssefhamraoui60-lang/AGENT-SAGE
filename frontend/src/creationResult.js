// A save attempt and a confirmed creation are distinct states.
export function creationResult(article){
 const outcome=article.outcome,operation=article.operation||{};
 if(!outcome&&!['executing','ambiguous','unverified','succeeded','failed'].includes(operation.status))return null;
 const sql=outcome?.sql_readback;
 const comparisons=outcome?.comparisons||{};
 const confirmed=outcome?.confirmed===true&&operation.status==='succeeded'&&operation.after_record?.exists===true&&sql?.ok===true&&sql.folder==='TEST'&&sql.article?.length===1&&typeof sql.article[0].ITMREF_0==='string'&&sql.article[0].ITMREF_0.trim()===article.code_article&&Object.keys(comparisons).length>=6&&Object.values(comparisons).every(x=>x===true);
 const code=confirmed?sql.article[0].ITMREF_0:article.code_article;
 if(confirmed)return {confirmed:true,label:'Création confirmée Sage + SQL',code,message:'Article enregistré dans TEST et vérifié par SOAP read et SQL SELECT. Vérification dans Sage : TEST → GESITM.'};
 if(operation.status==='failed')return {confirmed:false,label:'Création refusée par Sage',code,message:'La tentative a été refusée. Consultez les messages Sage et les relectures ; aucune relance automatique.'};
 if(['executing','ambiguous'].includes(operation.status))return {confirmed:false,label:'Résultat incertain — ne pas relancer',code,message:'L’article peut avoir été enregistré. Vérifier son existence par lecture Sage et SQL avant toute nouvelle décision.'};
 return {confirmed:false,label:'Vérification incomplète — ne pas relancer',code,message:'La tentative ne dispose pas de toutes les confirmations Sage et SQL. Aucun nouvel envoi automatique.'};
}
