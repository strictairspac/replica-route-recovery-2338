from fastapi import APIRouter,Depends
from fastapi.responses import Response
import json
from src.config.database import db_session
from src.utils.security import current,writer
from src.schemas.backup import BackupInput,RecoveryInput
from src.services import backups as bservice,recoveries as rservice
router=APIRouter()
@router.get('/backups')
def backups(db=Depends(db_session),user=Depends(current)):return bservice.listing(db)
@router.get('/backups/{ident}')
def backup_detail(ident:int,db=Depends(db_session),user=Depends(current)):return bservice.detail(db,ident)
@router.get('/backups/{ident}/recoveries')
def backup_recoveries(ident:int,db=Depends(db_session),user=Depends(current)):return bservice.dependents(db,ident)
@router.post('/backups',status_code=201)
def backup_create(data:BackupInput,db=Depends(db_session),user=Depends(writer)):return bservice.create(db,data,user)
@router.post('/backups/{ident}/retry')
def backup_retry(ident:int,db=Depends(db_session),user=Depends(writer)):return bservice.retry(db,ident,user)
@router.get('/recoveries')
def recoveries(db=Depends(db_session),user=Depends(current)):return rservice.listing(db)
@router.get('/recoveries/{ident}')
def recovery_detail(ident:int,db=Depends(db_session),user=Depends(current)):return rservice.detail(db,ident)
@router.post('/recoveries',status_code=201)
def recovery_create(data:RecoveryInput,db=Depends(db_session),user=Depends(writer)):return rservice.create(db,data,user)
@router.post('/recoveries/{ident}/retry')
def recovery_retry(ident:int,db=Depends(db_session),user=Depends(writer)):return rservice.retry(db,ident,user)
@router.get('/recoveries/{ident}/export')
def recovery_export(ident:int,db=Depends(db_session),user=Depends(current)):
    obj=rservice.detail(db,ident)
    return Response(json.dumps(obj,ensure_ascii=False,indent=2),media_type='application/json',
                    headers={'Content-Disposition':f'attachment; filename="recovery-{ident}.json"'})
