from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
import re
from app.delivery import dispatch_notification
from app.providers import send_email
from shared.database import init_db

app = FastAPI(title="OpsPulse Notifications", version="1.0.0")

@app.on_event("startup")
def startup():
    init_db()

class EmailInput(BaseModel):
    to: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=50000)

    @field_validator("to")
    @classmethod
    def validate_recipient(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("A valid email recipient is required")
        return value

@app.get("/health")
def health():
    return {"status": "ok", "service": "notification"}

@app.post("/dispatch")
def dispatch(event: dict):
    try:
        return dispatch_notification(event)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

@app.post("/email")
def email(body: EmailInput):
    return {"sent": send_email(body.to, body.subject, body.body)}
