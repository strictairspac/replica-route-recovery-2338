from sqlalchemy import select,func
from src.config.database import Session,Base,engine
from src.models.entities import User,Node,RequestSet,Trial,WriteWorkload,BackupJob,RecoveryJob
from src.utils.security import password_hash
from src.services.recovery_engine import normalize_writes,build_backup,restore_backup,EngineError

def seed():
    Base.metadata.create_all(engine)
    with Session() as db:
        for role in ('admin','operator','viewer'):
            email=role+'@qiyuan.test'
            if not db.scalar(select(User).where(User.email==email)):db.add(User(email=email,password=password_hash('Demo2026!'),role=role))
        for name,role,pos,delay,note in [('harbor-primary','primary',105,0,'栖原主站 · 写入航道'),('north-replica','replica',104,150,'北站副本 · 延迟偏高'),('south-replica','replica',105,20,'南站副本 · 常用读航道')]:
            if not db.scalar(select(Node).where(Node.name==name)):db.add(Node(name=name,role=role,status='healthy',lineage='qiyuan-log-01',position=pos,delay_ms=delay,note=note))
        mixed=[{'at_ms':0,'kind':'write','session':'lab-A'},{'at_ms':100,'kind':'read','session':'lab-A'},{'at_ms':600,'kind':'replicate','node':'south-replica','position':106,'delay_ms':20},{'at_ms':700,'kind':'read','session':'lab-A'},{'at_ms':800,'kind':'node_down','node':'south-replica'},{'at_ms':900,'kind':'read','session':'lab-A'},{'at_ms':1000,'kind':'node_down','node':'harbor-primary'},{'at_ms':1100,'kind':'read','session':'lab-A'}]
        cases=[('QY-1117-A','交接班写后读与双节点故障',mixed),('QY-1117-B','延迟超标回退主库',[{'at_ms':0,'kind':'node_down','node':'south-replica'},{'at_ms':10,'kind':'read','session':'visitor'}]),('QY-1117-C','双副本不可读时拒绝',[{'at_ms':0,'kind':'write','session':'lab-B'},{'at_ms':1000,'kind':'node_down','node':'harbor-primary'},{'at_ms':1100,'kind':'read','session':'lab-B'}])]
        for code,title,events in cases:
            if not db.scalar(select(RequestSet).where(RequestSet.code==code)):db.add(RequestSet(code=code,title=title,events=events,note='栖原站点值班交接 · 09:15 请求轨迹'))
        pitr_writes=[
            {'at_ms':100,'key':'route:harbor','value':'primary-105'},
            {'at_ms':200,'key':'route:north','value':'replica-104'},
            {'at_ms':300,'key':'route:south','value':'replica-105'},
            {'at_ms':400,'key':'route:harbor','value':'primary-106'},
            {'at_ms':400,'key':'route:north','value':'replica-105'},
            {'at_ms':500,'key':'route:south','value':'replica-106'},
            {'at_ms':600,'key':'route:harbor','value':'primary-107'},
            {'at_ms':700,'key':'route:north','value':'replica-106'},
            {'at_ms':800,'key':'route:south','value':'replica-107'},
            {'at_ms':900,'key':'route:harbor','value':'primary-108'},
            {'at_ms':1000,'key':'audit:shift','value':'sealed-20261117'},
            {'at_ms':1100,'key':'route:north','value':'replica-107'},
        ]
        wl=db.scalar(select(WriteWorkload).where(WriteWorkload.code=='WL-1117-PITR'))
        if not wl:
            wl=WriteWorkload(code='WL-1117-PITR',title='交接班键值写入与同刻提交',writes=pitr_writes,
                             note='含备份窗口并发写入与 at_ms=400 同刻双提交，用于备份中写入、同刻边界与缺段恢复验证')
            db.add(wl);db.flush()
        # 演示用在线备份（窗口 250–950ms，拷贝点 600ms）+ 三条恢复：成功、同刻边界、缺段失败。
        if not db.scalar(select(BackupJob).where(BackupJob.name=='demo-backup-250-950')):
            writes=normalize_writes(wl.writes)
            artifact,meta=build_backup(writes,250,950,600,'none')
            backup=BackupJob(name='demo-backup-250-950',workload_id=wl.id,start_ms=250,finish_ms=950,
                             copy_point_ms=600,corruption='none',status='completed',
                             artifact=artifact,backup_meta=meta)
            db.add(backup);db.flush()
            def add_recovery(name,target,missing):
                try:
                    result=restore_backup(artifact,target,missing_segment_nos=missing)
                    db.add(RecoveryJob(name=name,backup_id=backup.id,target_ms=target,missing_segments=missing,
                                       status='completed',attempts=1,result=result))
                except EngineError as exc:
                    db.add(RecoveryJob(name=name,backup_id=backup.id,target_ms=target,missing_segments=missing,
                                       status='failed',attempts=1,fail_code=exc.code,error=exc.message,
                                       result={'publishable':False,'fail_code':exc.code,'reason':exc.message}))
            add_recovery('demo-pitr-to-700',700,[])       # 成功：恢复到 700ms 已提交键值
            add_recovery('demo-pitr-boundary-400',400,[]) # 成功：同刻 seq4/5 边界验证
            add_recovery('demo-pitr-gap-fail',900,[2])    # 失败：缺段2，拒绝发布
        db.commit();print({cls.__tablename__:db.scalar(select(func.count()).select_from(cls)) for cls in (User,Node,RequestSet,Trial,WriteWorkload,BackupJob,RecoveryJob)})
if __name__=='__main__':seed()
