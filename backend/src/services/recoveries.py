import json
from fastapi import HTTPException
from sqlalchemy import select
from src.models.entities import BackupJob,RecoveryJob
from src.utils.serialization import record
from src.constants.enums import RUN_STATES
from src.services.recovery_engine import restore_backup,EngineError
from .backups import _enqueue,ARTIFACT_DIR
def listing(db):return [record(x) for x in db.scalars(select(RecoveryJob).order_by(RecoveryJob.id.desc()))]
def detail(db,ident):
    obj=db.get(RecoveryJob,ident)
    if not obj:raise HTTPException(404,'恢复任务不存在')
    return record(obj)
def create(db,data,user):
    backup=db.get(BackupJob,data.backup_id)
    if not backup:raise HTTPException(404,'备份不存在')
    if backup.status!='completed' or not backup.artifact:raise HTTPException(422,'所选备份尚未完成或无产物，不能发起恢复')
    if db.scalar(select(RecoveryJob).where(RecoveryJob.name==data.name)):
        raise HTTPException(409,'恢复任务名已存在，重试请使用原任务的重试入口，不覆盖旧试验')
    obj=RecoveryJob(name=data.name,backup_id=data.backup_id,target_ms=data.target_ms,
                    missing_segments=data.missing_segments,status=RUN_STATES[0],attempts=0)
    return _enqueue(db,obj,user,'定点恢复入队 '+data.name,'recovery')
def retry(db,ident,user):
    obj=db.get(RecoveryJob,ident)
    if not obj:raise HTTPException(404,'恢复任务不存在')
    if obj.status=='completed':raise HTTPException(409,'已完成恢复结果不可变；如需其他时刻请新建恢复任务')
    obj.status='queued';obj.error=None
    return _enqueue(db,obj,user,'重试定点恢复 '+obj.name,'recovery',retry=True)
def run_recovery(ident):
    """worker 调用：幂等定点恢复。重复消息/重试不会重复应用写入，也不覆盖既有结果与节点台账。"""
    from src.config.database import Session
    with Session() as db:
        obj=db.get(RecoveryJob,ident)
        if not obj:return
        if obj.status=='completed':return
        obj.status='running';obj.attempts=(obj.attempts or 0)+1;db.commit()
        backup=db.get(BackupJob,obj.backup_id)
        artifact=backup.artifact;target=obj.target_ms;missing=list(obj.missing_segments or [])
    try:
        result=restore_backup(artifact,target,missing_segment_nos=missing)
    except EngineError as e:
        with Session() as db:
            o=db.get(RecoveryJob,ident)
            o.status='failed';o.fail_code=e.code;o.error=e.message
            o.result={'publishable':False,'fail_code':e.code,'reason':e.message}
            db.commit()
        return
    with Session() as db:
        o=db.get(RecoveryJob,ident);o.result=result;o.fail_code=None;o.error=None;o.status='completed';db.commit()
    ARTIFACT_DIR.mkdir(parents=True,exist_ok=True)
    (ARTIFACT_DIR/f'recovery-{ident}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
