from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import router
app = FastAPI(title="OpsPulse API Gateway", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
@app.get("/health")
def health(): return {"status":"ok", "service":"gateway"}
