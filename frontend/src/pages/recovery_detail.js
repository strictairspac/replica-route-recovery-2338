import {table} from '../components/common/table.js';
import {badge} from '../components/common/badge.js';
import {esc,date} from '../utils/html.js';
import {session} from '../hooks/session.js';
import {FAIL_REASONS} from '../constants/enums.js';
const readonly=session.user?.role==='viewer';
const isPublishable=r=>Boolean(r&&(r.publishable===true||r.verification?.publishable===true));

export function recoveryDetailPage(job,backup){
  if(!job)return '<div class="empty">恢复任务不存在或尚未加载。</div>';
  const failed=job.status==='failed';const r=job.result;const publishable=isPublishable(r);
  return `<div class="evidence-top"><div>
      <span class="eyebrow">PITR EVIDENCE / RECOVERY #${job.id}</span>
      <h2>${esc(job.name)} ${badge(job.status)}</h2>
      <p>${date(job.created_at)} · 来源备份 #${job.backup_id}${backup?` · ${esc(backup.name)}`:''} · 目标 ${job.target_ms}ms · 已尝试 ${job.attempts} 次</p>
    </div><div><a href="#pitr"><button>← 返回备份恢复</button></a>
    ${publishable?` <button id="export-recovery" data-id="${job.id}">导出恢复证据 ↓</button>`:''}
    ${failed&&!readonly?` <button class="primary retry-recovery" data-id="${job.id}" style="width:auto;margin-left:8px">重试恢复任务</button>`:''}</div></div>
  ${job.status==='queued'||job.status==='running'?'<div class="notice">恢复任务执行中，页面每 1.5 秒自动刷新。</div>':''}
  ${failed?renderFailure(job):''}
  ${publishable?renderSuccess(job,backup):''}
  ${failed?`<div class="protocol"><h3>失败处置口径</h3><ol>
    <li>系统无法证明目标时刻的完整性时拒绝发布，绝不静默跳过缺段或坏段。</li>
    <li>重试复用同一任务，按 seq 幂等重放：不重复应用写入，也不覆盖任何既有节点与旧试验。</li>
    <li>若为缺段/损坏类失败，需补齐对应 WAL 段或换用完整备份后再发起新恢复。</li>
  </ol></div>`:''}`;
}

function renderFailure(job){
  const reason=FAIL_REASONS[job.fail_code]||job.error||job.fail_code;
  return `<div class="verdict" style="border-top-color:var(--red)"><div class="verdict-icon" style="color:var(--red)">✕</div><div>
      <span class="eyebrow">RECOVERY REJECTED / NO DATA PUBLISHED</span>
      <h2>恢复失败：${esc(reason)}</h2>
      <p>失败代码 <code>${esc(job.fail_code||'unknown')}</code> · 模拟缺段 ${(job.missing_segments||[]).join(',')||'无'} · 未写入任何恢复键值，现有数据与旧试验不受影响</p>
    </div></div>
  <div class="error">${esc(job.error||reason)}</div>`;
}

function renderSuccess(job,backup){
  const r=job.result;const replay=r.replay;
  const kvRows=r.restored_kv.map(x=>[esc(x.key),esc(x.value),`seq ${x.seq}`,`${x.at_ms}ms`]);
  const m=backup?.artifact?.manifest;
  const boundarySeqs=r.same_timestamp_seqs||[];
  return `<div class="verdict"><div class="verdict-icon">✓</div><div>
      <span class="eyebrow">VERIFIED PUBLISHABLE / GROUND-TRUTH MATCH</span>
      <h2>恢复内容与目标时刻已提交真值一致，允许发布</h2>
      <p>截止提交序号 ${r.cutoff_seq} · 恢复键值 ${r.restored_kv.length} 个 · 新应用 WAL ${replay.newly_applied_seqs.length} 条 · 快照重叠跳过 ${replay.snapshot_overlap_skips} 条</p>
    </div></div>
  <div class="policy-strip">目标时刻 ${r.target_ms}ms <span>／</span> 同刻提交 seq ${boundarySeqs.length?boundarySeqs.join(','):'无'} <span>／</span> 所需 WAL 段 ${replay.needed_segments.join(',')||'无'} <span>／</span> 内容校验 <code style="font-size:9px">${esc(r.restored_checksum.slice(0,32))}…</code></div>
  <div class="key-proof"><strong>同刻边界规则</strong><p>${esc(r.same_timestamp_boundary.rule)}</p>
    <p>本目标时刻纳入的同刻提交：${boundarySeqs.length?boundarySeqs.map(s=>`seq ${s}`).join('、'):'无'}；目标时刻之后的提交一律不纳入。</p></div>
  <div class="section-top"><h2>恢复后的键值内容</h2><span>RESTORED KEY-VALUE STATE</span></div>
  ${table(['键','恢复值','来源提交序号','提交时刻'],kvRows)}
  <div class="evidence-notes">
    <section><h3>重放与幂等证据</h3>
      <p>快照窗口前最大序号 ${replay.snapshot_max_seq}；新应用序号 [${replay.newly_applied_seqs.join(',')||'无'}]；重复跳过 ${replay.duplicate_skips} 条；模拟缺段命中 [${(replay.missing_segments_simulated||[]).join(',')||'无'}]。</p>
      <p>重试时同 seq 写入只跳过不覆盖，保证重复执行结果与校验和完全一致。</p></section>
    <section><h3>独立真值对账</h3>
      <p>${esc(r.verification.note)}</p>
      <p>真值路径：快照∪WAL 按 seq 去重重建完整日志后独立按目标时刻过滤，与“快照还原+重放”路径逐条比对。</p>
      <code>${esc(r.restored_checksum)}</code></section>
  </div>
  ${m?`<div class="notice">来源备份窗口 ${m.start_ms}→${m.finish_ms}ms、WAL seq ${m.wal_first_seq}–${m.wal_last_seq}；目标时刻晚于备份完成时刻时，恢复内容仅证明到备份完成时刻（cutoff=${r.cutoff_seq}）。</div>`:''}`;
}
