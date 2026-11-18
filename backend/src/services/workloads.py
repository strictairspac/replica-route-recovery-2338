from sqlalchemy import select
from fastapi import HTTPException
from src.models.entities import WriteWorkload
from src.utils.serialization import record
from src.services.recovery_engine import normalize_writes,EngineError
from .common import save
def listing(db):return [record(x) for x in db.scalars(select(WriteWorkload).order_by(WriteWorkload.id))]
def detail(db,ident):
    obj=db.get(WriteWorkload,ident)
    if not obj:raise HTTPException(404,'写入脚本不存在')
    return record(obj)
def create(db,data,user):
    try:normalize_writes(data.model_dump()['writes'])
    except EngineError as e:raise HTTPException(422,e.message)
    return save(db,WriteWorkload(**data.model_dump()),user,'创建写入脚本 '+data.code)
