from fastapi import APIRouter,Depends
from src.config.database import db_session
from src.utils.security import current,writer
from src.schemas.node import NodeInput
from src.services import nodes as service
router=APIRouter()
@router.get('/nodes')
def listing(db=Depends(db_session),user=Depends(current)):return service.listing(db)
@router.post('/nodes',status_code=201)
def create(data:NodeInput,db=Depends(db_session),user=Depends(writer)):return service.create(db,data,user)
@router.put('/nodes/{ident}')
def update(ident:int,data:NodeInput,db=Depends(db_session),user=Depends(writer)):return service.update(db,ident,data,user)
