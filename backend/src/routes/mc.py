from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from src.config.database import get_db
from src.controllers.dependencies import current_user,writers
from src.schemas.mc import McInput,McPatch
from src.services import mc_runs
from src.utils.serialize import row
router=APIRouter()
@router.get('/monte-carlo')
def index(db:Session=Depends(get_db),user=Depends(current_user)):return mc_runs.list_runs(db)
@router.get('/monte-carlo/{id}')
def detail(id:int,db:Session=Depends(get_db),user=Depends(current_user)):return row(mc_runs.get_run(db,id))
@router.post('/monte-carlo',status_code=201)
def create(data:McInput,db:Session=Depends(get_db),user=Depends(writers)):return mc_runs.create_run(db,data,user)
@router.patch('/monte-carlo/{id}/status')
def patch_status(id:int,data:McPatch,db:Session=Depends(get_db),user=Depends(writers)):return mc_runs.set_status(db,id,data.status,user)
