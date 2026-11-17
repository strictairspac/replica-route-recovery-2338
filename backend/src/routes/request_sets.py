from fastapi import APIRouter,Depends
from src.config.database import db_session
from src.utils.security import current,writer
from src.schemas.request_set import RequestSetInput
from src.services import request_sets as service
router=APIRouter()
@router.get('/request_sets')
def listing(db=Depends(db_session),user=Depends(current)):return service.listing(db)
@router.post('/request_sets',status_code=201)
def create(data:RequestSetInput,db=Depends(db_session),user=Depends(writer)):return service.create(db,data,user)
@router.put('/request_sets/{ident}')
def update(ident:int,data:RequestSetInput,db=Depends(db_session),user=Depends(writer)):return service.update(db,ident,data,user)
