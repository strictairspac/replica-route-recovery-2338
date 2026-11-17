from sqlalchemy import select,func
from fastapi import HTTPException
from src.models.entities import Node
from src.utils.serialization import record
from .common import save
def listing(db):return [record(x) for x in db.scalars(select(Node).order_by(Node.id))]
def validate(db,data,exclude=None):
    if not exclude and db.scalar(select(func.count()).select_from(Node))>=12:raise HTTPException(422,'最多12个节点')
    if data.role=='primary':
        query=select(Node).where(Node.role=='primary')
        if exclude:query=query.where(Node.id!=exclude)
        if db.scalar(query):raise HTTPException(422,'已有主节点，请修改现有主节点')
def create(db,data,user):
    validate(db,data);return save(db,Node(**data.model_dump()),user,'创建复制节点 '+data.name)
def update(db,ident,data,user):
    obj=db.get(Node,ident)
    if not obj:raise HTTPException(404,'节点不存在')
    validate(db,data,ident)
    for k,v in data.model_dump().items():setattr(obj,k,v)
    return save(db,obj,user,'更新复制节点 '+data.name)
