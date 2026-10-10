from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from shared.database import init_db
from app.endpoint import router

app = FastAPI(title="OpsPulse REST Alert Endpoint", version="1.0.0")

@app.on_event("startup")
def startup():
    init_db()

@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and detail.get("result") == "failure":
        content = detail
    else:
        content = {"result": "failure", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    # Do not leak exception internals or credentials in webhook responses.
    return JSONResponse(status_code=500, content={"result": "failure", "message": "Internal server error"})

@app.get("/health")
def health():
    return {"status": "ok", "service": "alert-routing"}

app.include_router(router)
