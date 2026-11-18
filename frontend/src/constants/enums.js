export const ROLES={admin:'管理员',operator:'操作员',viewer:'观察员'};
export const RUN_STATES={queued:'排队中',running:'执行中',completed:'已完成',failed:'失败'};
export const CORRUPTION_KINDS={none:'无损坏（完整备份）',snapshot_corrupt:'模拟备份拷贝损坏',manifest_corrupt:'模拟备份清单损坏'};
export const FAIL_REASONS={
  manifest_corrupt:'备份清单校验和不符，备份已损坏',
  snapshot_corrupt:'快照校验和不符，备份拷贝已损坏，存在数据丢失风险',
  artifact_malformed:'备份产物结构不完整',
  wal_disordered:'WAL 序号不连续，备份损坏',
  wal_segment_missing:'增量日志缺段，无法证明完整性，存在数据丢失风险',
  wal_segment_corrupt:'WAL 段校验和不符，日志损坏，存在数据丢失风险',
  wal_out_of_order:'WAL 序号回退，拒绝应用',
  verify_mismatch:'恢复结果与目标时刻已提交真值对账不一致，拒绝发布',
  coverage_gap:'备份覆盖不足，拒绝猜测恢复',
  target_before_backup:'目标时刻早于备份开始时刻，本备份不覆盖',
  bad_target_seq:'目标序号超出备份覆盖范围',
};
