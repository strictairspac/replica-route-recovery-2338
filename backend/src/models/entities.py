from sqlalchemy import Column,Integer,String,JSON,DateTime,Text,ForeignKey
from datetime import datetime,timezone
from src.config.database import Base
class User(Base):
    __tablename__='users'
    id=Column(Integer,primary_key=True);email=Column(String(120),unique=True,nullable=False);password=Column(String(300),nullable=False);role=Column(String(20),nullable=False)
class Node(Base):
    __tablename__='nodes'
    id=Column(Integer,primary_key=True);name=Column(String(80),unique=True,nullable=False);role=Column(String(20),nullable=False);status=Column(String(20),nullable=False)
    lineage=Column(String(80),nullable=False);position=Column(Integer,nullable=False);delay_ms=Column(Integer,nullable=False);note=Column(String(300),default='')
class RequestSet(Base):
    __tablename__='request_sets'
    id=Column(Integer,primary_key=True);code=Column(String(80),unique=True,nullable=False);title=Column(String(160),nullable=False);events=Column(JSON,nullable=False);note=Column(String(300),default='')
class Trial(Base):
    __tablename__='trials'
    id=Column(Integer,primary_key=True);name=Column(String(120),nullable=False);request_set_id=Column(Integer,ForeignKey('request_sets.id'),nullable=False)
    max_delay_ms=Column(Integer,nullable=False);sticky_ms=Column(Integer,nullable=False);status=Column(String(20),nullable=False,default='queued');input_snapshot=Column(JSON,nullable=False);result=Column(JSON,nullable=True);error=Column(Text,nullable=True)
    created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Audit(Base):
    __tablename__='audit_logs'
    id=Column(Integer,primary_key=True);actor=Column(String(120),nullable=False);action=Column(String(160),nullable=False);created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class WriteWorkload(Base):
    __tablename__='write_workloads'
    id=Column(Integer,primary_key=True);code=Column(String(80),unique=True,nullable=False);title=Column(String(160),nullable=False)
    writes=Column(JSON,nullable=False);note=Column(String(300),default='')
    created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class BackupJob(Base):
    __tablename__='backup_jobs'
    id=Column(Integer,primary_key=True);name=Column(String(120),nullable=False);workload_id=Column(Integer,ForeignKey('write_workloads.id'),nullable=False)
    start_ms=Column(Integer,nullable=False);finish_ms=Column(Integer,nullable=False);copy_point_ms=Column(Integer,nullable=False)
    corruption=Column(String(40),nullable=False,default='none');status=Column(String(20),nullable=False,default='queued');error=Column(Text,nullable=True)
    artifact=Column(JSON,nullable=True);backup_meta=Column(JSON,nullable=True)
    created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class RecoveryJob(Base):
    __tablename__='recovery_jobs'
    id=Column(Integer,primary_key=True);name=Column(String(120),unique=True,nullable=False);backup_id=Column(Integer,ForeignKey('backup_jobs.id'),nullable=False)
    target_ms=Column(Integer,nullable=False);missing_segments=Column(JSON,nullable=False,default=list)
    status=Column(String(20),nullable=False,default='queued');error=Column(Text,nullable=True);fail_code=Column(String(60),nullable=True)
    result=Column(JSON,nullable=True);attempts=Column(Integer,nullable=False,default=0)
    created_at=Column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
