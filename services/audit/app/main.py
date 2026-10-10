from fastapi import FastAPI, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from shared.database import get_db, init_db
from app.events import list_events
app=FastAPI(title="OpsPulse Audit")
@app.on_event("startup")
def startup(): init_db()
@app.get("/health")
def health(): return {"status":"ok","service":"audit"}
@app.get("/")
def events(limit:int=100,x_opspulse_organization_id:int|None=Header(default=None),db:Session=Depends(get_db)):
 if not x_opspulse_organization_id: raise HTTPException(401,"Organization context is missing")
 return list_events(db,limit,x_opspulse_organization_id)
