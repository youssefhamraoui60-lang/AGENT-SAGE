// Preserve stored history; collapse only consecutive duplicate assistant messages.
export function visibleMessages(messages=[]){
 const result=[];
 for(const message of messages){
  if(message.role==='tool')continue;
  const previous=result.at(-1);
  if(message.role==='assistant'&&previous?.role==='assistant'&&previous.content.trim()===message.content.trim()&&JSON.stringify(previous.payload?.supplier_snapshots)===JSON.stringify(message.payload?.supplier_snapshots))continue;
  result.push(message);
 }
 return result;
}

export function latestSupplierSnapshotId(messages=[]){
 const latest=messages.findLast(m=>m.role==='assistant');
 return latest?.payload?.supplier_snapshots?.length?latest.id:undefined;
}
