import os
import secrets
import pymysql
from fastapi import FastAPI, Form, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

app = FastAPI()
security = HTTPBasic()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

AUTH_USERNAME = "avijit"
AUTH_PASSWORD = "721517"

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "your_mysql_password",
    "database": "tg_dashboard",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

def get_db():
    try:
        return pymysql.connect(**DB_CONFIG)
    except Exception as e:
        print(f"[DB Warning] Could not connect to local MySQL: {e}")
        return None

def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, AUTH_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, AUTH_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/", response_class=HTMLResponse)
@app.get("/control", response_class=HTMLResponse)
async def control_console(request: Request, user: str = Depends(authenticate)):
    accounts, promos, settings = [], [], {
        "active_time_sec": 1800,
        "rest_time_sec": 180,
        "sleep_start_ist": "23:00:00",
        "sleep_end_ist": "07:00:00"
    }
    db = get_db()
    if db:
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT * FROM accounts ORDER BY id ASC")
                accounts = cursor.fetchall() or []
                cursor.execute("SELECT * FROM promo_messages ORDER BY id DESC")
                promos = cursor.fetchall() or []
                for p in promos:
                    cursor.execute("SELECT account_id FROM promo_account_map WHERE promo_id = %s", (p["id"],))
                    p["assigned_account_ids"] = [row["account_id"] for row in cursor.fetchall()]
                cursor.execute("SELECT * FROM settings WHERE id = 1")
                db_settings = cursor.fetchone()
                if db_settings:
                    settings = db_settings
            db.close()
        except Exception as e:
            print(f"Error fetching control data: {e}")

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"accounts": accounts, "promos": promos, "settings": settings}
    )

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(request: Request, user: str = Depends(authenticate)):
    accounts, logs = [], []
    db = get_db()
    if db:
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT * FROM accounts ORDER BY id ASC")
                accounts = cursor.fetchall() or []
                cursor.execute("SELECT * FROM activity_logs ORDER BY id DESC LIMIT 100")
                logs = cursor.fetchall() or []
            db.close()
        except Exception as e:
            print(f"Error fetching dashboard data: {e}")

    # Fallback preview nodes for demo purposes if local DB is empty/disconnected
    if not accounts:
        accounts = [
            {"id": 1, "phone": "+919876543210", "status": "active"},
            {"id": 2, "phone": "+919812345678", "status": "active"}
        ]

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"accounts": accounts, "logs": logs}
    )

@app.get("/api/logs")
async def get_logs_api(user: str = Depends(authenticate)):
    logs = []
    db = get_db()
    if db:
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT * FROM activity_logs ORDER BY id DESC LIMIT 50")
                logs = cursor.fetchall() or []
            db.close()
        except Exception as e:
            pass
    return {"logs": logs}
