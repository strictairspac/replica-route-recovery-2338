import {table} from '../components/common/table.js';
import {badge} from '../components/common/badge.js';
import {esc,date} from '../utils/html.js';
import {session} from '../hooks/session.js';
import {CORRUPTION_KINDS,FAIL_REASONS} from '../constants/enums.js';

const readonly=session.user?.role==='viewer';
const demoWrites=JSON.stringify([
  {at_ms:100,key:'route:harbor',value:'primary-105'},
  {at_ms:200,key:'route:north',value:'replica-104'},
  {at_ms:300,key:'route:south',value:'replica-105'},
  {at_ms:400,key:'route:harbor',value:'primary-106'},
  {at_ms:400,key:'route:north',value:'replica-105'},
  {at_ms:500,key:'route:south',value:'replica-106'},
],null,2);

function workloadPanel(workloads){
  return `<section class="form-panel"><span class="eyebrow">INTERLEAVED WRITE SCRIPT</span><h2>1 · 编排带键值写入时序</h2>
  <p class="help">写入按 at_ms 非递减编排，同刻写入按输入顺序分配提交序号 seq；备份窗口内的写入即为“备份期间并发写入”。</p>
  <form id="workload-form">
    <label>脚本编号<input name="code" value="WL-1117-PITR-2" required></label>
    <label>名称<input name="title" value="交接班键值写入演练" required></label>
    <label>写入 JSON（at_ms / key / value，最多 200 条）<textarea name="writes" rows="9" required>${esc(demoWrites)}</textarea></label>
    <label>备注<input name="note" value="可编排同刻提交与交错时序"></label>
    <button class="primary" ${readonly?'disabled':''}>保存写入脚本 +</button>
  </form></section>`;
}

function workloadTimeline(workloads){
  const rows=workloads.flatMap(wl=>wl.writes.map((w,i)=>[
    `<strong>${esc(wl.code)}</strong><small>#${i+1} seq=${i+1}</small>`,
    `${w.at_ms}ms`,esc(w.key),esc(w.value)
  ]));
  return `<div class="section-top"><h2>写入脚本与提交时序</h2><span>${workloads.length} SCRIPTS / KEY-VALUE COMMITS</span></div>
  ${table(['脚本 / 提交序号','时刻','键','值'],rows)}`;
}

function backupPanel(workloads,backups){
  const completed=backups.filter(b=>b.status==='completed');
  return `<section class="form-panel"><span class="eyebrow">ONLINE BACKUP / FUZZY SNAPSHOT + WAL</span><h2>2 · 发起在线备份</h2>
  <p class="help">备份从 start 到 finish 全程不阻塞写入；拷贝点 copy_point 之前的提交进模糊快照，窗口内全部提交进增量 WAL 分段。</p>
  <form id="backup-form">
    <label>备份任务名<input name="name" value="backup-window-250-950" required></label>
    <label>写入脚本<select name="workload_id">${workloads.map(w=>`<option value="${w.id}">${esc(w.code)} · ${esc(w.title)}</option>`).join('')}</select></label>
    <div class="fields">
      <label>窗口开始 start_ms<input name="start_ms" type="number" min="0" value="250" required></label>
      <label>窗口完成 finish_ms<input name="finish_ms" type="number" min="0" value="950" required></label>
    </div>
    <label>拷贝点 copy_point_ms（留空取窗口中点）<input name="copy_point_ms" type="number" min="0" placeholder="如 600"></label>
    <label>损坏模拟<select name="corruption">${Object.entries(CORRUPTION_KINDS).map(([v,l])=>`<option value="${v}">${esc(l)}</option>`).join('')}</select></label>
    <button class="primary" ${readonly?'disabled':''}>入队在线备份 ↗</button>
  </form>
  <p class="help">已完成备份 ${completed.length} 个，可在下方第 3 步选择并定点恢复。</p></section>`;
}

function backupTable(backups,workloads){
  const wlName=id=>workloads.find(w=>w.id===id)?.code||`#${id}`;
  return table(['备份任务 / 时间','脚本','窗口 start→finish / 拷贝点','损坏模拟','状态','操作'],
    backups.map(b=>[
      `<strong>${esc(b.name)}</strong><small>#${b.id} · ${date(b.created_at)}</small>`,
      esc(wlName(b.workload_id)),
      `${b.start_ms} → ${b.finish_ms}<small>copy_point=${b.copy_point_ms}ms</small>`,
      esc(CORRUPTION_KINDS[b.corruption]||b.corruption),
      badge(b.status),
      `<a href="#backup/${b.id}">备份详情 →</a>${b.status==='failed'&&!readonly?` <button class="small retry-backup" data-id="${b.id}">重试</button>`:''}${b.error?`<small class="rejected">${esc(b.error)}</small>`:''}`
    ]));
}

function recoveryPanel(backups){
  const completed=backups.filter(b=>b.status==='completed');
  return `<section class="form-panel"><span class="eyebrow">POINT-IN-TIME RECOVERY</span><h2>3 · 定点恢复演练</h2>
  <p class="help">同刻边界：at_ms ≤ 目标时刻 的提交全部纳入。缺段/坏段无法证明完整时任务明确失败，拒绝发布。</p>
  <form id="recovery-form">
    <label>恢复任务名（唯一，重试走原任务入口）<input name="name" value="pitr-to-700" required></label>
    <label>选择已完成备份<select name="backup_id" ${completed.length?'':'disabled'}>
      ${completed.length?completed.map(b=>`<option value="${b.id}">${esc(b.name)} #${b.id}（WAL seq ${b.artifact.manifest.start_seq}–${b.artifact.manifest.end_seq}）</option>`).join(''):'<option>暂无已完成备份</option>'}
    </select></label>
    <label>目标时刻 target_ms<input name="target_ms" type="number" min="0" value="700" required></label>
    <label>模拟缺段编号（逗号分隔，备份内局部段号；留空表示不缺段）<input name="missing_segments" placeholder="如 2 或 1,3"></label>
    <button class="primary" ${readonly||!completed.length?'disabled':''}>入队恢复任务 ↗</button>
  </form></section>`;
}

function recoveryTable(recoveries,backups){
  const bName=id=>backups.find(b=>b.id===id)?.name||`备份#${id}`;
  return table(['恢复任务 / 时间','来源备份','目标时刻','缺段模拟','状态 / 失败原因','操作'],
    recoveries.map(r=>{
      const failed=r.status==='failed';
      return [
        `<strong>${esc(r.name)}</strong><small>#${r.id} · 尝试 ${r.attempts} 次 · ${date(r.created_at)}</small>`,
        esc(bName(r.backup_id)),
        `${r.target_ms}ms`,
        (r.missing_segments&&r.missing_segments.length)?r.missing_segments.join(','):'无',
        `${badge(r.status)}${failed?`<small class="rejected">${esc(FAIL_REASONS[r.fail_code]||r.error||r.fail_code)}</small>`:''}`,
        `<a href="#recovery/${r.id}">恢复证据 →</a>${failed&&!readonly?` <button class="small retry-recovery" data-id="${r.id}">重试</button>`:''}`
      ];
    }));
}

export function pitrPage({workloads,backups,recoveries}){
  return `<div class="split">
    <section>
      ${workloadTimeline(workloads)}
      <div class="section-top"><h2>在线备份任务</h2><span>SNAPSHOT + WAL SEGMENTS</span></div>
      ${backupTable(backups,workloads)}
      <div class="section-top"><h2>定点恢复任务</h2><span>QUEUED → RUNNING → COMPLETED / FAILED</span></div>
      ${recoveryTable(recoveries,backups)}
      <div class="protocol"><h3>可写性与恢复确定性的代价</h3><ol>
        <li>备份全程可并发写入：快照只是 copy_point 时刻的模糊拷贝，窗口内写入可能只进快照、只进 WAL 或两者都进。</li>
        <li>正确性依赖从 start_seq 起连续的 WAL：恢复时快照中窗口区间条目被确定性丢弃，WAL 对窗口内提交具有权威效力。</li>
        <li>恢复按 seq 幂等重放：重试不重复应用写入、不覆盖现有节点与旧试验；代价是 RTO 随窗口写入量线性增长。</li>
        <li>任何所需 WAL 段缺失/损坏、快照或清单校验失败，都无法证明完整，任务明确失败并拒绝发布。</li>
      </ol></div>
    </section>
    <div>
      ${workloadPanel(workloads)}
      <div style="height:24px"></div>
      ${backupPanel(workloads,backups)}
      <div style="height:24px"></div>
      ${recoveryPanel(backups)}
    </div>
  </div>`;
}
