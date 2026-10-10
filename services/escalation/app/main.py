from fastapi import FastAPI
from shared.database import init_db
from app.schedules import router
app=FastAPI(title="OpsPulse On-call and Escalation")
@app.on_event("startup")
def startup(): init_db()
app.include_router(router)
@app.get("/health")
def health(): return {"status":"ok","service":"escalation"}
