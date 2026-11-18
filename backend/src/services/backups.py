import json,os
from pathlib import Path
from sqlalchemy import select
from fastapi import HTTPException
from src.models.entities import WriteWorkload,BackupJob,RecoveryJob
from src.utils.serialization import record
from src.constants.enums import RUN_STATES
from src.services.recovery_engine import normalize_writes,build_backup,EngineError
ARTIFACT_DIR=Path(os.getenv('ARTIFACT_DIR','/artifacts/pitr'))
QUEUE_KEY='replicaroute:queue'
def listing(db):return [record(x) for x in db.scalars(select(BackupJob).order_by(BackupJob.id.desc()))]
def detail(db,ident):
    obj=db.get(BackupJob,ident)
    if not obj:raise HTTPException(404,'备份任务不存在')
    return record(obj)
def _load_workload(db,workload_id):
    wl=db.get(WriteWorkload,workload_id)
    if not wl:raise HTTPException(404,'写入脚本不存在')
    try:return normalize_writes(wl.writes)
    except EngineError as e:raise HTTPException(422,e.message)
def create(db,data,user):
    writes=_load_workload(db,data.workload_id)
    # 入队前先试算窗口，非法时序/空窗口在入队前 422，避免产生注定失败的任务。
    try:build_backup(writes,data.start_ms,data.finish_ms,data.copy_point_ms,data.corruption)
    except EngineError as e:raise HTTPException(422,e.message)
    obj=BackupJob(name=data.name,workload_id=data.workload_id,start_ms=data.start_ms,finish_ms=data.finish_ms,
                  copy_point_ms=data.copy_point_ms,corruption=data.corruption,status=RUN_STATES[0])
    return _enqueue(db,obj,user,'在线备份入队 '+data.name,'backup')
def retry(db,ident,user):
    obj=db.get(BackupJob,ident)
    if not obj:raise HTTPException(404,'备份任务不存在')
    if obj.status=='completed':raise HTTPException(409,'已完成备份不可重试；如需其他窗口请新建备份任务')
    obj.status='queued';obj.error=None
    return _enqueue(db,obj,user,'重试在线备份 '+obj.name,'backup',retry=True)
def _enqueue(db,obj,user,action,kind,retry=False):
    from src.services.trials import queue
    if not retry:db.add(obj)
    db.commit()
    payload=json.dumps({'kind':kind,'id':obj.id})
    try:queue.rpush(QUEUE_KEY,payload)
    except Exception:
        obj.status='failed';obj.error='队列暂时不可用，请重试';db.commit();raise HTTPException(503,obj.error)
    from src.models.entities import Audit
    db.add(Audit(actor=user.email,action=action));db.commit()
    return record(obj)
def run_backup(ident):
    """worker 调用：执行在线备份。可重复调用，产物按任务 id 覆盖但绝不影响其他任务/节点台账。"""
    from src.config.database import Session
    with Session() as db:
        obj=db.get(BackupJob,ident)
        if not obj:return
        if obj.status=='completed':return  # 幂等：已完成不重复执行
        obj.status='running';db.commit()
        wl=db.get(WriteWorkload,obj.workload_id)
        writes=normalize_writes(wl.writes)
    try:
        artifact,meta=build_backup(writes,obj.start_ms,obj.finish_ms,obj.copy_point_ms,obj.corruption)
    except EngineError as e:
        with Session() as db:
            o=db.get(BackupJob,ident);o.status='failed';o.error=e.message;db.commit()
        return
    with Session() as db:
        o=db.get(BackupJob,ident);o.artifact=artifact;o.backup_meta=meta;o.status='completed';db.commit()
    ARTIFACT_DIR.mkdir(parents=True,exist_ok=True)
    (ARTIFACT_DIR/f'backup-{ident}.json').write_text(json.dumps(artifact,ensure_ascii=False,indent=2))
def dependents(db,backup_id):
    return [record(x) for x in db.scalars(select(RecoveryJob).where(RecoveryJob.backup_id==backup_id).order_by(RecoveryJob.id))]
