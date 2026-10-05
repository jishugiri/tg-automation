import pymysql
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from telethon import TelegramClient
from telethon.sessions import StringSession

app = FastAPI()
templates = Jinja2Templates(directory="templates")

temp_sessions = {}

# --- Set Your MySQL Credentials Here ---
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Cse@2021",  # <-- Change this to your MySQL password
    "database": "tg_dashboard",
    "cursorclass": pymysql.cursors.DictCursor
}

def get_db():
    return pymysql.connect(**DB_CONFIG)

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("SELECT * FROM accounts")
        accounts = cursor.fetchall()
        cursor.execute("SELECT * FROM promo_messages")
        promos = cursor.fetchall()
        cursor.execute("SELECT * FROM settings WHERE id = 1")
        settings = cursor.fetchone()
    db.close()
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "accounts": accounts,
        "promos": promos,
        "settings": settings
    })

@app.post("/auth/send-otp")
async def send_otp(phone: str = Form(...), api_id: int = Form(...), api_hash: str = Form(...)):
    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.connect()
    sent = await client.send_code_request(phone)
    
    temp_sessions[phone] = {
        "client": client,
        "phone_code_hash": sent.phone_code_hash,
        "api_id": api_id,
        "api_hash": api_hash
    }
    return {"status": "otp_sent"}

@app.post("/auth/verify-login")
async def verify_login(phone: str = Form(...), code: str = Form(...), password: str = Form(None)):
    if phone not in temp_sessions:
        return JSONResponse(status_code=400, content={"error": "Session expired. Try again."})
    
    session_data = temp_sessions[phone]
    client: TelegramClient = session_data["client"]
    
    try:
        if password:
            await client.sign_in(phone=phone, code=code, password=password)
        else:
            await client.sign_in(phone=phone, code=code, phone_code_hash=session_data["phone_code_hash"])
        
        session_string = client.session.save()
        
        db = get_db()
        with db.cursor() as cursor:
            cursor.execute(
                """INSERT INTO accounts (phone, api_id, api_hash, session_string)
                   VALUES (%s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE session_string=%s, status='active'""",
                (phone, session_data["api_id"], session_data["api_hash"], session_string, session_string)
            )
            db.commit()
        db.close()
        
        await client.disconnect()
        del temp_sessions[phone]
        return {"status": "success", "message": "Account successfully connected!"}
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.post("/promo/add")
async def add_promo(title: str = Form(...), content: str = Form(...)):
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute("INSERT INTO promo_messages (title, content) VALUES (%s, %s)", (title, content))
        db.commit()
    db.close()
    return {"status": "success"}

@app.post("/promo/assign")
async def assign_promo(promo_id: int = Form(...), account_id: int = Form(None)):
    db = get_db()
    with db.cursor() as cursor:
        if account_id:
            cursor.execute("UPDATE promo_messages SET assigned_account_id = NULL WHERE assigned_account_id = %s", (account_id,))
        cursor.execute("UPDATE promo_messages SET assigned_account_id = %s WHERE id = %s", (account_id, promo_id))
        db.commit()
    db.close()
    return {"status": "success"}

@app.post("/settings/update")
async def update_settings(
    active_time: int = Form(...),
    rest_time: int = Form(...),
    sleep_start: str = Form(...),
    sleep_end: str = Form(...)
):
    db = get_db()
    with db.cursor() as cursor:
        cursor.execute(
            """UPDATE settings SET active_time_sec=%s, rest_time_sec=%s, 
               sleep_start_ist=%s, sleep_end_ist=%s WHERE id=1""",
            (active_time, rest_time, sleep_start, sleep_end)
        )
        db.commit()
    db.close()
    return {"status": "success"}