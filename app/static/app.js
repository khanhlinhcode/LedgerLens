(() => {
 'use strict';
 let apiKey = ''; let previousQuestion = 'Doanh thu theo phòng ban';
 const $ = (id) => document.getElementById(id);
 const vn = (n) => Number(n || 0).toLocaleString('vi-VN', { maximumFractionDigits: 2 });
 const show = (msg) => { const t = $('toast');t.textContent=msg;t.style.display='block';clearTimeout(show.timer);show.timer=setTimeout(()=>t.style.display='none',4800);};
 const authOpen = () => { $('authOverlay').classList.add('open');$('authOverlay').setAttribute('aria-hidden','false');$('apiKey').focus();};
 const authClose = () => { $('authOverlay').classList.remove('open');$('authOverlay').setAttribute('aria-hidden','true');};
 async function request(path, opts={}) {
   if (!apiKey) { authOpen();throw Error('Enter your local API key first.'); }
   const headers = { 'X-API-Key': apiKey, ...(opts.headers || {}) };
   const r=await fetch(path,{...opts,headers,cache:'no-store'});
   if (!r.ok) {let detail=`HTTP ${r.status}`; try{const x=await r.json();detail=x.detail||detail;}catch{}; if(r.status===401) authOpen(); throw Error(detail);}
   return r;
 }
 async function json(path,opts){const r=await request(path,opts);return r.json();}
 async function download(path,opts,filename){const r=await request(path,opts);const blob=await r.blob();const u=URL.createObjectURL(blob);const a=document.createElement('a');a.href=u;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),2000);show('Report exported: '+filename);}
 function chart(data){const el=$('barChart');el.replaceChildren();if(!data.length){el.textContent='Upload an Excel workbook to see data.';el.classList.add('empty');return;}el.classList.remove('empty');
   const items=data.slice(0,10),max=Math.max(1,...items.map(x=>Math.max(x.revenue,x.expense)));
   for(const d of items){const col=document.createElement('div');col.className='chart-col';const bars=document.createElement('div');bars.className='bars';for(const [kind,v] of [['rev',d.revenue],['exp',d.expense]]){const b=document.createElement('div');b.className='bar '+kind;b.style.height=`${Math.max(v ? 3 : 0,(v/max)*165)}px`;b.title=`${d.group}: ${kind==='rev'?'Revenue':'Expense'} ${vn(v)} VND`;bars.append(b);}const txt=document.createElement('span');txt.className='chart-label';txt.textContent=d.group;col.append(bars,txt);el.append(col);}
 }
 async function refresh(){ const d=await json('/api/overview');$('revenue').textContent=vn(d.totals.REVENUE);$('expense').textContent=vn(d.totals.EXPENSE);$('net').textContent=vn(d.net);$('recordCount').textContent=vn(d.count);$('batchCount').textContent=d.batch_count;$('rejected').textContent=d.rejected_rows;$('duplicates').textContent=d.duplicate_rows;
   const grouped=await json('/api/reports/summary?group_by='+encodeURIComponent($('grouping').value));chart(grouped.groups);
   const records=await json('/api/records?limit=20');const body=$('recordBody');body.replaceChildren();if(!records.length){const row=body.insertRow();const cell=row.insertCell();cell.colSpan=8;cell.className='empty-td';cell.textContent='No accepted records yet.';} else for(const r of records){const tr=body.insertRow();const source=`${r.source_file} · ${r.source_sheet}:${r.source_row}`;[r.date,r.document_no,r.department,r.counterparty,r.entry_type,vn(r.amount_vnd),r.status,source].forEach(v=>{const td=tr.insertCell();td.textContent=v;});}
 }
 $('authButton').addEventListener('click',authOpen);$('closeAuth').addEventListener('click',authClose);
 $('authForm').addEventListener('submit',async(e)=>{e.preventDefault();apiKey=$('apiKey').value;try{await refresh();$('authError').textContent='';$('apiKey').value='';authClose();show('Workspace connected.');}catch(err){$('authError').textContent=err.message;apiKey='';}});
 $('grouping').addEventListener('change',()=>refresh().catch(e=>show(e.message)));
 $('downloadSummary').addEventListener('click',()=>download('/api/reports/summary.xlsx?group_by='+$('grouping').value,{},'ledgerlens-summary.xlsx').catch(e=>show(e.message)));
 async function upload(files){for(const f of files){try{const body=new FormData();body.append('file',f);const result=await json('/api/imports',{method:'POST',body});$('importResult').textContent=`${f.name} · ${result.accepted} accepted, ${result.rejected} rejected, ${result.duplicates} duplicates. ${result.issues.length} quality log items.`;show('Imported '+result.accepted+' accepted rows from '+f.name);}catch(e){$('importResult').textContent=f.name+' · '+e.message;show(e.message);}}await refresh();}
 $('uploadFiles').addEventListener('change',(e)=>upload([...e.target.files]).catch(e=>show(e.message)));
 const dz=$('dropZone');dz.addEventListener('dragover',(e)=>{e.preventDefault();dz.classList.add('drag');});dz.addEventListener('dragleave',()=>dz.classList.remove('drag'));dz.addEventListener('drop',(e)=>{e.preventDefault();dz.classList.remove('drag');upload([...e.dataTransfer.files]).catch(e=>show(e.message));});
 document.querySelectorAll('.prompt').forEach(b=>b.addEventListener('click',()=>{$('question').value=b.textContent;$('question').focus();}));
 $('askForm').addEventListener('submit',async(e)=>{e.preventDefault();const q=$('question').value.trim();if(q.length<3)return;previousQuestion=q;try{const r=await json('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q})});$('answer').replaceChildren();const sym=document.createElement('span');sym.className='assistant-icon';sym.textContent='✧';const txt=document.createElement('div');txt.textContent=`${r.answer} Grouped by ${r.intent.group_by}. ${r.report.groups.length} groups. ${r.caveat}`;$('answer').append(sym,txt);$('planner').textContent='Planner: '+r.planner+' · Query: allowlisted';}catch(e){show(e.message);}});
 $('downloadAnswer').addEventListener('click',()=>download('/api/ask/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:previousQuestion})},'ledgerlens-ai-answer.xlsx').catch(e=>show(e.message)));
 document.querySelectorAll('.navitem').forEach(a=>a.addEventListener('click',()=>{document.querySelectorAll('.navitem').forEach(b=>b.classList.remove('active'));a.classList.add('active');}));
 authOpen();
})();
