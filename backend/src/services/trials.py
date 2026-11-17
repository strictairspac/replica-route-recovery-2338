from sqlalchemy import select
from redis import Redis
from fastapi import HTTPException
from src.models.entities import Node,RequestSet,Trial
from src.config.settings import REDIS_URL
from src.constants.enums import RUN_STATES
from src.utils.serialization import record
from .common import save
from .routing import simulate
queue=Redis.from_url(REDIS_URL,decode_responses=True)
def listing(db):return [record(x) for x in db.scalars(select(Trial).order_by(Trial.id.desc()))]
def detail(db,ident):
    obj=db.get(Trial,ident)
    if not obj:raise HTTPException(404,'试验不存在')
    return record(obj)
def create(db,data,user):
    req=db.get(RequestSet,data.request_set_id)
    if not req:raise HTTPException(404,'请求集不存在')
    nodes=[record(x) for x in db.scalars(select(Node).order_by(Node.id))]
    try:simulate(nodes,req.events,data.max_delay_ms,data.sticky_ms)
    except ValueError as e:raise HTTPException(422,str(e))
    snapshot={'nodes':nodes,'request_set':record(req)};obj=Trial(**data.model_dump(),input_snapshot=snapshot,status=RUN_STATES[0]);result=save(db,obj,user,'路由演练入队 '+data.name)
    try:queue.rpush('replicaroute:queue',str(obj.id))
    except Exception:
        obj.status='failed';obj.error='队列暂时不可用，请重新创建';db.commit();raise HTTPException(503,obj.error)
    return result
