from typing import Literal
from pydantic import BaseModel,Field,model_validator
class Event(BaseModel):
    at_ms:int=Field(ge=0,le=86400000)
    kind:Literal['write','read','replicate','node_down','node_up']
    session:str=Field(default='default',min_length=1,max_length=60)
    node:str|None=Field(default=None,max_length=80)
    position:int|None=Field(default=None,ge=0,le=1000000000)
    delay_ms:int|None=Field(default=None,ge=0,le=3600000)
    @model_validator(mode='after')
    def valid_event(self):
        if self.kind in ('replicate','node_down','node_up') and not self.node:raise ValueError('节点事件需要node')
        if self.kind=='replicate' and (self.position is None or self.delay_ms is None):raise ValueError('replicate需要position和delay_ms')
        return self
class RequestSetInput(BaseModel):
    code:str=Field(min_length=2,max_length=80)
    title:str=Field(min_length=2,max_length=160)
    events:list[Event]=Field(min_length=1,max_length=100)
    note:str=Field(default='',max_length=300)
    @model_validator(mode='after')
    def chronological(self):
        if any(a.at_ms>b.at_ms for a,b in zip(self.events,self.events[1:])):raise ValueError('事件必须按at_ms非递减排列')
        return self
