import {api,download,downloadRecovery} from './api/client.js';import {nodesStore} from './stores/nodes.js';import {request_setsStore} from './stores/request_sets.js';import {trialsStore} from './stores/trials.js';import {workloadsStore} from './stores/workloads.js';import {backupsStore} from './stores/backups.js';import {session} from './hooks/session.js';import {feedback} from './hooks/feedback.js';import {formValues} from './utils/forms.js';import {esc,date} from './utils/html.js';import {frame} from './components/common/frame.js';import {table} from './components/common/table.js';import {loginPage} from './pages/login.js';import {nodesPage} from './pages/nodes.js';import {requestSetsPage} from './pages/request_sets.js';import {trialsPage} from './pages/trials.js';import {evidencePage} from './pages/evidence.js';import {pitrPage} from './pages/pitr.js';import {backupDetailPage} from './pages/backup_detail.js';import {recoveryDetailPage} from './pages/recovery_detail.js';import {titles} from './router/routes.js';
let timer=null;const app=document.querySelector('#app');
function bindForm(id,path,transform,after){document.querySelector(id)?.addEventListener('submit',async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{const data=transform(formValues(e.target));const ident=data.id;delete data.id;const result=await api(path+(ident?'/'+ident:''),ident?'PUT':'POST',data);await after(result);feedback(ident?'保存成功，记录已更新。':'保存成功，任务已入队或记录已更新。')}catch(err){feedback(err.message.includes('JSON')?'JSON格式错误，请检查引号与逗号':err.message,true)}finally{b.disabled=false}})}
const busy=s=>['queued','running'].includes(s);
async function render(){clearTimeout(timer);if(!session.token){app.innerHTML=loginPage();bindForm('#login','/auth/login',x=>x,async x=>{session.save(x);location.hash='nodes';await render()});return}
try{await api('/auth/me');
await Promise.all([nodesStore.refresh(),request_setsStore.refresh(),trialsStore.refresh(),workloadsStore.refresh(),backupsStore.refresh()]);
const [page='nodes',id]=location.hash.slice(1).split('/');
const nodes=nodesStore.items,sets=request_setsStore.items,trials=trialsStore.items,
      workloads=workloadsStore.items,{backups,recoveries}=backupsStore;
let content,trial,keepPolling=false;
if(page==='request_sets')content=requestSetsPage(sets);
else if(page==='trials')content=trialsPage(trials,sets);
else if(page==='evidence'){trial=id?await api('/trials/'+id):trials[0];content=evidencePage(trial)}
else if(page==='pitr')content=pitrPage({workloads,backups,recoveries});
else if(page==='backup'){const backup=id?await api('/backups/'+id):backups[0];const wl=workloads.find(w=>w.id===backup?.workload_id);const deps=backup?await api('/backups/'+backup.id+'/recoveries'):[];content=backupDetailPage(backup,wl,deps);if(backup&&busy(backup.status))keepPolling=true}
else if(page==='recovery'){const job=id?await api('/recoveries/'+id):recoveries[0];const backup=job?backups.find(b=>b.id===job.backup_id):null;content=recoveryDetailPage(job,backup);if(job&&busy(job.status))keepPolling=true}
else if(page==='audit'){const rows=await api('/audit');content=table(['时间','操作人','动作'],rows.map(x=>[date(x.created_at),esc(x.actor),esc(x.action)]))}
else content=nodesPage(nodes);
const [title,subtitle]=titles[page]||titles.nodes;
app.innerHTML=frame(page,title,subtitle,content);
document.querySelector('#logout').onclick=()=>{session.clear();render()};
bindForm('#node-form','/nodes',x=>({...x,position:Number(x.position),delay_ms:Number(x.delay_ms)}),render);
bindForm('#request-form','/request_sets',x=>({...x,events:JSON.parse(x.events)}),render);
bindForm('#trial-form','/trials',x=>({...x,request_set_id:Number(x.request_set_id),max_delay_ms:Number(x.max_delay_ms),sticky_ms:Number(x.sticky_ms)}),async x=>{location.hash='evidence/'+x.id;await render()});
bindForm('#workload-form','/workloads',x=>({...x,writes:JSON.parse(x.writes)}),render);
bindForm('#backup-form','/backups',x=>({...x,workload_id:Number(x.workload_id),start_ms:Number(x.start_ms),finish_ms:Number(x.finish_ms),copy_point_ms:x.copy_point_ms===''?null:Number(x.copy_point_ms),corruption:x.corruption||'none'}),render);
bindForm('#recovery-form','/recoveries',x=>({...x,backup_id:Number(x.backup_id),target_ms:Number(x.target_ms),missing_segments:x.missing_segments?String(x.missing_segments).split(',').map(s=>Number(s.trim())).filter(n=>Number.isInteger(n)&&n>0):[]}),async x=>{location.hash='recovery/'+x.id;await render()});
document.querySelectorAll('.edit-node').forEach(b=>b.onclick=()=>{const n=nodes.find(x=>x.id===Number(b.dataset.id)),form=document.querySelector('#node-form');for(const key of ['id','name','role','status','lineage','position','delay_ms','note'])form.elements[key].value=n[key];document.querySelector('#node-heading').textContent='修改节点 #'+n.id;form.scrollIntoView({behavior:'smooth',block:'center'})});
document.querySelectorAll('.edit-request').forEach(b=>b.onclick=()=>{const s=sets.find(x=>x.id===Number(b.dataset.id)),form=document.querySelector('#request-form');for(const key of ['id','code','title','note'])form.elements[key].value=s[key];form.elements.events.value=JSON.stringify(s.events,null,2);document.querySelector('#request-heading').textContent='修改请求集 #'+s.id;form.scrollIntoView({behavior:'smooth',block:'center'})});
document.querySelector('#export')?.addEventListener('click',async e=>{try{await download(e.target.dataset.id);feedback('路由JSON已下载')}catch(err){feedback(err.message,true)}});
document.querySelector('#export-recovery')?.addEventListener('click',async e=>{try{await downloadRecovery(e.target.dataset.id);feedback('恢复证据JSON已下载')}catch(err){feedback(err.message,true)}});
document.querySelectorAll('.retry-backup').forEach(b=>b.addEventListener('click',async()=>{try{await api('/backups/'+b.dataset.id+'/retry','POST');feedback('备份任务已重新入队');await render()}catch(err){feedback(err.message,true)}}));
document.querySelectorAll('.retry-recovery').forEach(b=>b.addEventListener('click',async()=>{try{const r=await api('/recoveries/'+b.dataset.id+'/retry','POST');feedback('恢复任务已重新入队（不覆盖旧结果）');location.hash='recovery/'+r.id;await render()}catch(err){feedback(err.message,true)}}));
const pitrBusy=page==='pitr'&&(backups.some(b=>busy(b.status))||recoveries.some(r=>busy(r.status)));
if((page==='evidence'&&trial&&busy(trial.status))||(page==='trials'&&trials.some(x=>busy(x.status)))||pitrBusy||keepPolling)timer=setTimeout(render,1500);
}catch(err){if(err.message.includes('登录')||err.message.includes('Not authenticated')){session.clear();await render()}else{if(!document.querySelector('#feedback'))app.innerHTML='<main><div id="feedback"></div><button onclick="location.reload()">重新加载</button></main>';feedback(err.message,true)}}}
window.addEventListener('hashchange',render);render();
