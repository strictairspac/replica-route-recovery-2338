import {table} from '../components/common/table.js';
import {badge} from '../components/common/badge.js';
import {esc,date} from '../utils/html.js';
import {session} from '../hooks/session.js';
import {CORRUPTION_KINDS} from '../constants/enums.js';
const readonly=session.user?.role==='viewer';

export function backupDetailPage(backup,workload,recoveries){
  if(!backup)return '<div class="empty">备份任务不存在或尚未加载。</div>';
  const m=backup.artifact?.manifest;
  return `<div class="evidence-top"><div>
      <span class="eyebrow">ONLINE BACKUP EVIDENCE / #${backup.id}</span>
      <h2>${esc(backup.name)} ${badge(backup.status)}</h2>
      <p>${date(backup.created_at)} · 脚本 ${esc(workload?.code||backup.workload_id)} · ${esc(CORRUPTION_KINDS[backup.corruption]||backup.corruption)}</p>
    </div><a href="#pitr"><button>← 返回备份恢复</button></a></div>
  ${backup.error?`<div class="error">${esc(backup.error)}</div>`:''}
  ${!m?'<div class="notice">备份尚未完成，产物未生成。完成后此处展示快照、WAL 分段与校验和。</div>':renderArtifact(backup,workload,recoveries)}`;
}

function renderArtifact(backup,workload,recoveries){
  const m=backup.artifact.manifest;const meta=backup.backup_meta||{};
  const windowSeqs=new Set(meta.window_write_seqs||[]);
  const snapSeqs=new Set(meta.snapshot_window_seqs||[]);
  const timeline=(workload?.writes||[]).map((w,i)=>{
    const seq=i+1;const inWindow=windowSeqs.has(seq);const inSnap=snapSeqs.has(seq);
    return [`seq ${seq}<small>${w.at_ms}ms</small>`,esc(w.key),esc(w.value),
      inWindow?`<span class="attribute">窗口内并发写入</span>`:'窗口外',
      inSnap?'<span class="attribute">已进模糊快照</span>':(inWindow?'仅在 WAL 中':'窗口前状态')];
  });
  const segRows=backup.artifact.segments.map(s=>[
    `段 ${s.segment_no}<small>seq ${s.seq_from}–${s.seq_to} · ${s.entries.length} 条</small>`,
    s.entries.map(e=>`${e.seq}:${esc(e.key)}`).join('<br>'),
    `<code style="font-size:9px">${esc(s.checksum.slice(0,24))}…</code>`
  ]);
  const snapRows=backup.artifact.snapshot.map(x=>[`seq ${x.seq}<small>${x.at_ms}ms</small>`,esc(x.key),esc(x.value)]);
  return `<div class="verdict"><div class="verdict-icon">${backup.corruption==='none'?'✓':'!'}</div><div>
      <span class="eyebrow">FUZZY SNAPSHOT + INCREMENTAL WAL</span>
      <h2>窗口 ${m.start_ms}→${m.finish_ms}ms，拷贝点 ${m.copy_point_ms}ms</h2>
      <p>WAL 覆盖 seq ${m.wal_first_seq}–${m.wal_last_seq} · 快照 ${m.snapshot_entry_count} 条 · WAL 段 ${m.segments.length} 个 · 窗口内并发写入 ${windowSeqs.size} 条</p>
    </div></div>
  <div class="policy-strip">清单校验 <code style="font-size:9px">${esc(m.manifest_checksum.slice(0,32))}…</code><span>／</span>快照校验 <code style="font-size:9px">${esc(m.snapshot_checksum.slice(0,32))}…</code><span>／</span>衔接规则：seq ≥ start_seq 的快照条目确定性丢弃，窗口内以 WAL 为准</div>
  <div class="section-top"><h2>备份中写入验证（交错时序）</h2><span>WINDOW WRITES / SNAPSHOT OVERLAP</span></div>
  ${table(['提交序号 / 时刻','键','值','窗口归属','快照归属'],timeline)}
  <div class="evidence-notes">
    <section><h3>模糊快照内容（copy_point 及之前）</h3>
      ${snapRows.length?table(['序号 / 时刻','键','值'],snapRows):'<div class="empty">快照为空（拷贝点早于首条写入）。</div>'}
    </section>
    <section><h3>增量 WAL 分段与校验和</h3>
      ${table(['段号 / 序号区间','包含提交','段校验和'],segRows)}
    </section>
  </div>
  <div class="section-top"><h2>基于该备份的恢复任务（${recoveries.length}）</h2><span>RECOVERY TRIALS</span></div>
  ${recoveries.length?table(['恢复任务','目标时刻','缺段','状态','证据'],recoveries.map(r=>[esc(r.name),`${r.target_ms}ms`,(r.missing_segments||[]).join(',')||'无',badge(r.status),`<a href="#recovery/${r.id}">查看 →</a>`])):'<div class="empty">暂无恢复任务，可在「备份恢复」页第 3 步选择本备份发起。</div>'}
  <div class="form-panel" style="margin-top:26px"><span class="eyebrow">QUICK RECOVERY FROM THIS BACKUP</span>
    <form id="recovery-form" class="inline-recovery">
      <input type="hidden" name="backup_id" value="${backup.id}">
      <label>恢复任务名<input name="name" value="pitr-b${backup.id}-${m.copy_point_ms}" required></label>
      <div class="fields">
        <label>目标时刻 target_ms<input name="target_ms" type="number" min="0" value="${m.finish_ms}" required></label>
        <label>模拟缺段（逗号分隔）<input name="missing_segments" placeholder="留空=不缺段"></label>
      </div>
      <button class="primary" ${readonly?'disabled':''}>入队定点恢复 ↗</button>
    </form></div>`;
}
