from pydantic import BaseModel,Field,model_validator
class WriteItem(BaseModel):
    at_ms:int=Field(ge=0,le=86400000)
    key:str=Field(min_length=1,max_length=120)
    value:str=Field(min_length=1,max_length=500)
class WorkloadInput(BaseModel):
    code:str=Field(min_length=2,max_length=80)
    title:str=Field(min_length=2,max_length=160)
    writes:list[WriteItem]=Field(min_length=1,max_length=200)
    note:str=Field(default='',max_length=300)
    @model_validator(mode='after')
    def chronological(self):
        if any(a.at_ms>b.at_ms for a,b in zip(self.writes,self.writes[1:])):
            raise ValueError('写入必须按 at_ms 非递减编排，同刻写入按输入顺序分配提交序号')
        return self
