from typing import Literal
from pydantic import BaseModel,Field
class NodeInput(BaseModel):
    name:str=Field(min_length=2,max_length=80)
    role:Literal['primary','replica']
    status:Literal['healthy','down']='healthy'
    lineage:str=Field(min_length=2,max_length=80)
    position:int=Field(ge=0,le=1000000000)
    delay_ms:int=Field(ge=0,le=3600000)
    note:str=Field(default='',max_length=300)
