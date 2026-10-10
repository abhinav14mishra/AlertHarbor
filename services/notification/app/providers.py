import os, smtplib
from email.message import EmailMessage

def send_email(to:str, subject:str, body:str)->bool:
    host=os.getenv("SMTP_HOST", "localhost"); port=int(os.getenv("SMTP_PORT","1025")); user=os.getenv("SMTP_USERNAME",""); password=os.getenv("SMTP_PASSWORD",""); use_tls=os.getenv("SMTP_TLS","false").lower()=="true"
    msg=EmailMessage(); msg["To"]=to; msg["From"]=(os.getenv("SMTP_FROM") or user or "opspulse@localhost"); msg["Subject"]=subject; msg.set_content(body)
    with smtplib.SMTP(host,port,timeout=10) as server:
        if use_tls: server.starttls()
        if user: server.login(user,password)
        server.send_message(msg)
    return True
