from typing import Literal
from pydantic import BaseModel,Field,model_validator
from src.constants.enums import CORRUPTION_KINDS
class BackupInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    workload_id:int=Field(gt=0)
    start_ms:int=Field(ge=0,le=86400000)
    finish_ms:int=Field(ge=0,le=86400000)
    copy_point_ms:int|None=Field(default=None,ge=0,le=86400000)
    corruption:Literal['none','snapshot_corrupt','manifest_corrupt']='none'
    @model_validator(mode='after')
    def window_ok(self):
        if self.start_ms>self.finish_ms:raise ValueError('备份开始时刻不能晚于完成时刻')
        cp=self.copy_point_ms if self.copy_point_ms is not None else (self.start_ms+self.finish_ms)//2
        if not (self.start_ms<=cp<=self.finish_ms):raise ValueError('拷贝点必须位于备份窗口 [start_ms, finish_ms] 内')
        self.copy_point_ms=cp
        if self.corruption not in CORRUPTION_KINDS:raise ValueError('未知损坏模拟类型')
        return self
class RecoveryInput(BaseModel):
    name:str=Field(min_length=2,max_length=120)
    backup_id:int=Field(gt=0)
    target_ms:int=Field(ge=0,le=86400000)
    missing_segments:list[int]=Field(default_factory=list,max_length=50)
    @model_validator(mode='after')
    def segs_ok(self):
        if any(not isinstance(x,int) or x<=0 for x in self.missing_segments):
            raise ValueError('缺段编号必须为正整数')
        if len(set(self.missing_segments))!=len(self.missing_segments):
            raise ValueError('缺段编号不能重复')
        return self
