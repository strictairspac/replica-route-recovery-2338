"""确定性在线备份与定点恢复（PITR）演练引擎。

模型（受控演练，不连接真实数据库）：
- 写入带键值，按提交时刻 at_ms 非递减排序，逐条分配单调提交序号 seq（1..N，同刻按输入顺序）。
- 在线备份 = 模糊快照（仅含 copy_point 及之前已提交写入，copy_point 位于备份窗口 [start_ms, finish_ms] 内，
  因此窗口内并发写入只可能部分进入快照）+ 增量 WAL 分段（从 start_ms 前最后一条提交之后开始，覆盖备份期间全部写入）。
- 恢复 = 快照还原（仅取窗口前状态）+ 按序号幂等重放 WAL，直到目标时刻（同刻边界：at_ms <= target_ms 的提交全部纳入，之后的不纳入）。
  模糊快照中属于窗口区间（seq >= start_seq）的条目确定性丢弃：WAL 对窗口内提交具有权威效力，
  因此即使拷贝点晚于目标时刻，也能把键回滚到目标时刻的旧值，而不会被快照中的未来值锁死。
- 校验：快照/段/清单各自 SHA256；恢复结果与“按目标时刻直接过滤完整写入日志”的真值独立对账，不一致则拒绝发布。
- 损坏模拟：snapshot_corrupt（破坏快照内容但保留旧校验和）/ manifest_corrupt（清单字段与实物不符）；
  缺段/坏段恢复：段缺失或段校验和不符即明确失败，绝不静默跳过（有数据丢失风险）。

代价（写性能与恢复确定性）：
- 可写性：备份全程不阻塞写入；代价是快照不具时间点一致性，正确性完全依赖从 start_seq 开始的连续 WAL。
- 确定性：恢复是 seq 幂等重放，重复应用不改变结果；代价是 RTO 随窗口内写入量线性增长，
  且任何一段 WAL 缺失/损坏都无法证明完整性，恢复直接失败，不允许带缺失发布。
"""
import hashlib
import json
from collections import OrderedDict

SEGMENT_SIZE = 4  # 每段最多 4 条提交，便于演练缺段


class EngineError(Exception):
    """可向用户展示的演练失败，携带机器可读 code。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _sha256(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def normalize_writes(raw_writes):
    """校验并规范化写入脚本，返回带提交序号的完整写入日志。"""
    if not isinstance(raw_writes, list) or not raw_writes:
        raise EngineError('empty_workload', '写入脚本至少包含一条带键值写入')
    if len(raw_writes) > 200:
        raise EngineError('workload_too_large', '单个写入脚本最多 200 条写入')
    writes, last_at = [], -1
    for i, item in enumerate(raw_writes):
        for field in ('at_ms', 'key', 'value'):
            if field not in item:
                raise EngineError('bad_write', f'第 {i + 1} 条写入缺少字段 {field}')
        at, key, value = item['at_ms'], str(item['key']), str(item['value'])
        if not isinstance(at, int) or at < 0 or at > 86400000:
            raise EngineError('bad_write', f'第 {i + 1} 条写入 at_ms 越界（0–86400000 整数）')
        if at < last_at:
            raise EngineError('write_order', f'第 {i + 1} 条写入时刻回退，写入必须按 at_ms 非递减编排')
        if not key or len(key) > 120 or len(value) > 500:
            raise EngineError('bad_write', f'第 {i + 1} 条写入键/值长度非法（键 1–120，值 1–500）')
        last_at = at
        writes.append({'seq': i + 1, 'at_ms': at, 'key': key, 'value': value})
    return writes


def _state_of(writes, upto_seq):
    """upto_seq（含）之前提交写入的键值真值；同一键取最大 seq。"""
    state = OrderedDict()
    for w in writes[:upto_seq]:
        state[w['key']] = {'value': w['value'], 'seq': w['seq'], 'at_ms': w['at_ms']}
    return state


def _state_at(writes, target_ms):
    """目标时刻真值：at_ms <= target_ms 的全部已提交写入。"""
    upto = 0
    for w in writes:
        if w['at_ms'] <= target_ms:
            upto = w['seq']
        else:
            break
    return _state_of(writes, upto), upto


def build_backup(writes, start_ms, finish_ms, copy_point_ms, corruption='none'):
    """构造一次在线备份的产物（快照 + WAL 分段 + 清单）。全程不修改写入日志，模拟窗口内可并发写入。"""
    if not (0 <= start_ms <= copy_point_ms <= finish_ms <= 86400000):
        raise EngineError('bad_window', '备份窗口必须满足 0 ≤ start ≤ copy_point ≤ finish ≤ 86400000')
    # 窗口前最后一条已提交写入；WAL 从其后一条（start_seq）开始，保证与快照无缝衔接。
    pre = [w for w in writes if w['at_ms'] < start_ms]
    start_seq = (pre[-1]['seq'] + 1) if pre else 1
    windowed = [w for w in writes if start_ms <= w['at_ms'] <= finish_ms]
    if not windowed:
        raise EngineError('empty_window', '备份窗口内没有写入，无法演练“备份期间并发写入”，请调整窗口')
    end_seq = windowed[-1]['seq']
    if copy_point_ms < start_ms:
        raise EngineError('bad_copy_point', '拷贝点不能早于备份开始时刻')
    snap_entries = [w for w in writes if w['at_ms'] <= copy_point_ms]
    snapshot = [
        {'key': w['key'], 'value': w['value'], 'seq': w['seq'], 'at_ms': w['at_ms']}
        for w in snap_entries
    ]
    snapshot_checksum = _sha256(snapshot)
    # WAL 分段：覆盖 start_seq..end_seq（备份从开始到完成期间的全部提交）。
    # 段号为备份内局部连续编号（1..k），每段固定 SEGMENT_SIZE 条，边界以清单位点为准。
    wal = [w for w in writes if start_seq <= w['seq'] <= end_seq]
    segments = []
    for idx in range(0, len(wal), SEGMENT_SIZE):
        chunk = wal[idx:idx + SEGMENT_SIZE]
        entries = [
            {'seq': w['seq'], 'at_ms': w['at_ms'], 'key': w['key'], 'value': w['value']}
            for w in chunk
        ]
        segments.append({
            'segment_no': idx // SEGMENT_SIZE + 1,
            'seq_from': chunk[0]['seq'],
            'seq_to': chunk[-1]['seq'],
            'entries': entries,
            'checksum': _sha256(entries),
        })
    segment_index = [
        {'segment_no': s['segment_no'], 'seq_from': s['seq_from'], 'seq_to': s['seq_to'],
         'entry_count': len(s['entries']), 'checksum': s['checksum']}
        for s in segments
    ]
    manifest = {
        'format': 'qiyuan-pitr-v1',
        'start_ms': start_ms,
        'finish_ms': finish_ms,
        'copy_point_ms': copy_point_ms,
        'start_seq': start_seq,
        'end_seq': end_seq,
        'snapshot_entry_count': len(snapshot),
        'snapshot_checksum': snapshot_checksum,
        'segments': segment_index,
        'wal_first_seq': start_seq,
        'wal_last_seq': end_seq,
    }
    # 损坏注入必须先于校验和计算：破坏内容但保留旧校验和，恢复端校验才能稳定发现。
    if corruption == 'snapshot_corrupt':
        if snapshot:
            snapshot[0]['value'] = snapshot[0]['value'] + '#CORRUPTED'
        else:
            raise EngineError('cannot_corrupt', '空快照无法注入快照损坏，请调整窗口')
    elif corruption == 'manifest_corrupt':
        manifest['end_seq'] = end_seq + 1  # 清单声称的 WAL 末端与实物不符
    elif corruption != 'none':
        raise EngineError('bad_corruption', '未知损坏类型')
    manifest['manifest_checksum'] = _sha256(
        {k: v for k, v in manifest.items() if k != 'manifest_checksum'}
    )
    if corruption == 'manifest_corrupt':
        # 用篡改前的正确校验和覆盖：恢复端重算必然不符，稳定触发 manifest_corrupt。
        manifest['manifest_checksum'] = _sha256({**manifest, 'end_seq': end_seq})
    truth_at_finish, _ = _state_at(writes, finish_ms)
    artifact = {
        'manifest': manifest,
        'snapshot': snapshot,
        'segments': segments,
    }
    meta = {
        'window_write_seqs': [w['seq'] for w in windowed],
        'snapshot_window_seqs': [w['seq'] for w in windowed if w['at_ms'] <= copy_point_ms],
        'ground_truth_at_finish': truth_at_finish,
    }
    return artifact, meta


def _verify_manifest(manifest):
    stored = manifest.get('manifest_checksum')
    body = {k: v for k, v in manifest.items() if k != 'manifest_checksum'}
    if not stored or _sha256(body) != stored:
        raise EngineError('manifest_corrupt', '备份清单校验和不符，备份已损坏，拒绝恢复')


def restore_backup(artifact, target_ms, missing_segment_nos=None, target_seq=None):
    """从备份产物定点恢复到 target_ms；返回恢复结果与对账证据，无法证明完整时 raise。"""
    missing = set(missing_segment_nos or [])
    manifest, snapshot, segments = artifact.get('manifest'), artifact.get('snapshot'), artifact.get('segments')
    if not isinstance(manifest, dict) or not isinstance(snapshot, list) or not isinstance(segments, list):
        raise EngineError('artifact_malformed', '备份产物结构不完整，拒绝恢复')
    _verify_manifest(manifest)
    # 1) 快照自检：模糊快照只保证 copy_point 一致，校验和保证字节未损坏。
    if _sha256(snapshot) != manifest['snapshot_checksum']:
        raise EngineError('snapshot_corrupt', '快照校验和不符，备份拷贝已损坏，存在数据丢失风险，拒绝发布')
    if any(s['seq_to'] > manifest['end_seq'] for s in segments):
        raise EngineError('manifest_corrupt', '清单位点与 WAL 实物不一致，备份损坏，拒绝恢复')
    # 2) 确定目标提交序号（同刻边界：<= target_ms 全纳入）。
    all_wal = [e for s in segments for e in s['entries']]
    if [e['seq'] for e in all_wal] != list(range(manifest['wal_first_seq'], manifest['wal_last_seq'] + 1)):
        raise EngineError('wal_disordered', 'WAL 序号不连续，备份损坏，拒绝恢复')
    if target_ms < manifest['start_ms']:
        raise EngineError('target_before_backup', '目标时刻早于备份开始时刻，本备份不覆盖该时刻，拒绝猜测恢复')
    cutoff = manifest['start_seq'] - 1
    for e in all_wal:
        if e['at_ms'] <= target_ms:
            cutoff = e['seq']
    if target_seq is not None:
        if not isinstance(target_seq, int) or target_seq < 0 or target_seq > manifest['end_seq']:
            raise EngineError('bad_target_seq', '目标序号超出备份覆盖范围')
        cutoff = target_seq
    # 3) 段完整性检查：重放区间 [start_seq, cutoff] 涉及的每一段都必须在位且校验和正确。
    #    段号是备份内局部编号，按清单中每段的实际序号区间求交集，不假设全局对齐。
    index = {s['segment_no']: s for s in segments}
    needed_nos = sorted(
        s['segment_no'] for s in segments
        if s['seq_from'] <= cutoff and s['seq_to'] >= manifest['start_seq']
    )
    missing_hits, checksum_bad = [], []
    for no in needed_nos:
        seg = index.get(no)
        if seg is None or no in missing:
            missing_hits.append(no)
            continue
        if _sha256(seg['entries']) != seg['checksum']:
            checksum_bad.append(no)
    if missing_hits:
        raise EngineError(
            'wal_segment_missing',
            f"增量日志缺段 {missing_hits}，无法证明到序号 {cutoff} 的完整性，存在数据丢失风险，恢复失败",
        )
    if checksum_bad:
        raise EngineError(
            'wal_segment_corrupt',
            f"WAL 段 {checksum_bad} 校验和不符，日志损坏，存在数据丢失风险，恢复失败",
        )
    # 4) 还原快照 + 幂等重放（seq 去重：重复应用同一写入不改变结果）。
    #    衔接规则：WAL 从 start_seq 起对窗口区间具有权威效力；模糊快照中 seq >= start_seq 的
    #    重叠条目是“拷贝点晚于备份开始”的产物，确定性丢弃，快照只负责提供窗口前状态（seq < start_seq）。
    #    这样即使 copy_point 晚于目标时刻，也能靠 WAL 把键回滚到目标时刻的旧值，而不是被快照未来值锁死。
    restored = OrderedDict()
    applied, replay_duplicates, overlap_skips = [], 0, 0
    for item in snapshot:
        if item['seq'] >= manifest['start_seq']:
            overlap_skips += 1
            continue
        restored[item['key']] = {'value': item['value'], 'seq': item['seq'], 'at_ms': item['at_ms']}
    snapshot_max_seq = max((x['seq'] for x in snapshot if x['seq'] < manifest['start_seq']), default=manifest['start_seq'] - 1)
    for e in all_wal:
        if e['seq'] > cutoff:
            break
        current = restored.get(e['key'])
        if current and current['seq'] >= e['seq']:
            replay_duplicates += 1  # 同序号重试消息：跳过而不是覆盖，保证重试幂等
            continue
        restored[e['key']] = {'value': e['value'], 'seq': e['seq'], 'at_ms': e['at_ms']}
        applied.append(e['seq'])
    # 5) 独立真值对账：用快照∪WAL 按 seq 去重重建“本备份可证明的完整日志”，再按目标时刻独立过滤，
    #    不经过快照还原/重放路径。两条路径结果一致才允许发布。
    journal_by_seq = {x['seq']: {'seq': x['seq'], 'at_ms': x['at_ms'], 'key': x['key'], 'value': x['value']}
                      for x in snapshot}
    for e in all_wal:
        journal_by_seq.setdefault(e['seq'], {'seq': e['seq'], 'at_ms': e['at_ms'], 'key': e['key'], 'value': e['value']})
    full_journal = [journal_by_seq[k] for k in sorted(journal_by_seq)]
    expected, expected_upto = _state_at(full_journal, target_ms)
    if target_seq is not None:
        expected = _state_of(full_journal, target_seq)
        expected_upto = target_seq
    # 目标时刻之后才提交的键不属于该时刻状态（与 actual 的时间过滤口径一致）。
    expected = OrderedDict((k, v) for k, v in expected.items() if v['at_ms'] <= target_ms)
    if cutoff != expected_upto:
        raise EngineError(
            'coverage_gap',
            f'目标时刻对应提交序号 {expected_upto} 与可重放序号 {cutoff} 不一致，备份覆盖不足，拒绝猜测恢复',
        )
    actual = OrderedDict(
        (k, v) for k, v in restored.items()
        if v['seq'] <= cutoff and v['at_ms'] <= target_ms
    )
    actual_sig = {k: (v['value'], v['seq'], v['at_ms']) for k, v in actual.items()}
    expected_sig = {k: (v['value'], v['seq'], v['at_ms']) for k, v in expected.items()}
    if actual_sig != expected_sig:
        raise EngineError('verify_mismatch', '恢复结果与目标时刻已提交真值对账不一致，拒绝发布')
    content_checksum = _sha256(actual_sig)  # 按键排序，与构造路径无关，保证可复现
    same_ms_seqs = [e['seq'] for e in all_wal if e['at_ms'] == target_ms]
    result = {
        'publishable': True,
        'target_ms': target_ms,
        'cutoff_seq': cutoff,
        'same_timestamp_seqs': same_ms_seqs,
        'same_timestamp_boundary': {
            'rule': 'at_ms <= target_ms 的提交全部纳入，at_ms > target_ms 的不纳入；同刻按 seq 顺序全部生效',
            'included': same_ms_seqs,
        },
        'restored_kv': [
            {'key': k, 'value': v['value'], 'seq': v['seq'], 'at_ms': v['at_ms']}
            for k, v in actual.items()
        ],
        'restored_checksum': content_checksum,
        'expected_checksum': content_checksum,
        'replay': {
            'snapshot_max_seq': snapshot_max_seq,
            'newly_applied_seqs': applied,
            'duplicate_skips': replay_duplicates,
            'snapshot_overlap_skips': overlap_skips,
            'needed_segments': needed_nos,
            'missing_segments_simulated': sorted(missing & set(needed_nos)),
        },
        'verification': {
            'ground_truth_upto_seq': expected_upto,
            'match': True,
            'publishable': True,
            'note': '恢复键值与目标时刻全部已提交写入逐条对账一致，证明完整，允许发布',
        },
    }
    return result
