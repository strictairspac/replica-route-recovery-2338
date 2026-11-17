from sqlalchemy import select
from fastapi import HTTPException
from src.models.entities import RequestSet
from src.utils.serialization import record
from .common import save
def listing(db):return [record(x) for x in db.scalars(select(RequestSet).order_by(RequestSet.id))]
def create(db,data,user):return save(db,RequestSet(**data.model_dump()),user,'创建会话请求集 '+data.code)
def update(db,ident,data,user):
    obj=db.get(RequestSet,ident)
    if not obj:raise HTTPException(404,'请求集不存在')
    for k,v in data.model_dump().items():setattr(obj,k,v)
    return save(db,obj,user,'更新会话请求集 '+data.code)
