ROLES = ('admin', 'operator', 'viewer')
RUN_STATES = ('queued', 'running', 'completed', 'failed')
CORRUPTION_KINDS = ('none', 'snapshot_corrupt', 'manifest_corrupt')
RECOVERY_FAIL_CODES = (
    'manifest_corrupt', 'snapshot_corrupt', 'artifact_malformed', 'wal_disordered',
    'wal_segment_missing', 'wal_segment_corrupt', 'wal_out_of_order',
    'verify_mismatch', 'target_before_backup', 'bad_target_seq',
)
