from fastapi import APIRouter,Depends
from src.config.database import db_session
from src.utils.security import current,writer
from src.schemas.workload import WorkloadInput
from src.services import workloads as service
router=APIRouter()
@router.get('/workloads')
def listing(db=Depends(db_session),user=Depends(current)):return service.listing(db)
@router.get('/workloads/{ident}')
def detail(ident:int,db=Depends(db_session),user=Depends(current)):return service.detail(db,ident)
@router.post('/workloads',status_code=201)
def create(data:WorkloadInput,db=Depends(db_session),user=Depends(writer)):return service.create(db,data,user)
