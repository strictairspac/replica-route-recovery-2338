import traceback,json
from pathlib import Path
from src.config.database import Session
from src.models.entities import Trial
from src.services.trials import queue
from src.services.routing import simulate
from src.services.backups import run_backup
from src.services.recoveries import run_recovery
def run_trial(ident):
    with Session() as db:
        obj=db.get(Trial,ident)
        if not obj:return
        if obj.status=='completed':return
        obj.status='running';db.commit()
        snapshot=obj.input_snapshot;delay=obj.max_delay_ms;sticky=obj.sticky_ms
    result=simulate(snapshot['nodes'],snapshot['request_set']['events'],delay,sticky)
    with Session() as db:
        obj=db.get(Trial,ident)
        if obj.status=='completed':return
        obj.result=result;obj.status='completed';db.commit()
    Path(f'/artifacts/route-{ident}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
while True:
    Path('/tmp/worker-heartbeat').touch()
    item=queue.blpop('replicaroute:queue',timeout=2)
    if not item:continue
    raw=item[1]
    try:
        envelope=json.loads(raw)
        kind,ident=envelope['kind'],int(envelope['id'])
    except (ValueError,KeyError,TypeError):
        kind,ident='trial',int(raw)  # 兼容旧版纯 ID 消息
    try:
        if kind=='trial':run_trial(ident)
        elif kind=='backup':run_backup(ident)
        elif kind=='recovery':run_recovery(ident)
        else:raise ValueError('未知任务类型 '+str(kind))
    except Exception:
        traceback.print_exc()
        # 兜底：run_backup/run_recovery 已在内部处理可预期的 EngineError；
        # 此处仅兜住未预期异常，保证任何任务都不会永久卡在 running。
        if kind=='trial':
            with Session() as db:
                obj=db.get(Trial,ident)
                if obj and obj.status!='completed':obj.status='failed';obj.error='后台执行异常，请重试';db.commit()
        elif kind in ('backup','recovery'):
            from src.models.entities import BackupJob,RecoveryJob
            model=BackupJob if kind=='backup' else RecoveryJob
            with Session() as db:
                obj=db.get(model,ident)
                if obj and obj.status!='completed':obj.status='failed';obj.error='后台执行异常，请重试';db.commit()
