export function analysisStatus(job,state){
 if(job?.status==='completed'&&job.phase?.startsWith('supplier_'))return 'Demande traitée. Aucune écriture effectuée par ce message.';
 if(['failed','interrupted','verification_incomplete'].includes(job?.status))return 'Vos informations sont conservées. Vous pouvez poursuivre dans le chat.';
 if(job?.status==='completed'&&state?.articles?.length){
  if(state.articles.every(a=>a.outcome?.confirmed))return 'Création vérifiée.';
  if(state.articles.some(a=>a.execution?.route==='general_test'&&a.execution.blockers?.length))return 'Création bloquée — action nécessaire.';
  if(state.articles.some(a=>a.operation?.status==='prepared'))return 'Données exactes prêtes à approuver.';
 }
 const states={queued:'Demande enregistrée. Analyse en attente.',extracting:'Extraction des informations en cours.',extracted:'Informations conservées. Préparation des vérifications.',verifying:'Vérification des référentiels Sage X3.',completed:'Brouillons prêts à relire.',verification_incomplete:'Informations conservées ; vérifications incomplètes.',failed:'Analyse interrompue. La demande est conservée.',interrupted:'Traitement interrompu. Reprise disponible.'};
 return states[job?.status]||'Suivi de votre demande.';
}
export async function followAnalysisJob({api,path,onUpdate,isCurrent=()=>true,delay=ms=>new Promise(resolve=>setTimeout(resolve,ms))}){
 let failures=0, polls=0;
 while(isCurrent()){
  if(++polls>270)throw new Error('Le traitement prend plus de temps que prévu. Votre demande est conservée ; le suivi se rétablira automatiquement.');
  let value;
  try{value=await api(path);failures=0;}catch(error){
   if(error.status&&![502,503,504].includes(error.status)||++failures>4)throw error;
   await delay(Math.min(1000*2**failures,8000));continue;
  }
  onUpdate(value);
  if(value.job.status==='completed')return value;
  if(['failed','interrupted','verification_incomplete'].includes(value.job.status)){
   return value;
  }
  if(value.job.resumable&&!value.job.worker_active)return value;
  await delay(1000);
 }
}
