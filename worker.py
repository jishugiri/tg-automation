import asyncio
import re
import random
import string
from datetime import datetime, time, timedelta
import pytz
import pymysql
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, SlowModeWaitError, UserBannedInChannelError, ChatWriteForbiddenError

# --- MySQL Configuration ---
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Cse@2021",
    "database": "tg_dashboard",
    "cursorclass": pymysql.cursors.DictCursor
}

def get_db():
    return pymysql.connect(**DB_CONFIG)

def clean_base_text(text: str) -> str:
    cleaned = re.sub(r'(#?ref_?\d+#?)', '', text, flags=re.IGNORECASE)
    return cleaned.strip()

def generate_unique_ref() -> str:
    digits = ''.join(random.choices(string.digits, k=random.randint(6, 8)))
    patterns = [
        f"#ref_{digits}",
        f"ref_{digits}#",
        f"#ref{digits}",
        f"ref_{digits}"
    ]
    return random.choice(patterns)

def to_time_obj(val):
    if isinstance(val, timedelta):
        total_seconds = int(val.total_seconds())
        hours = (total_seconds // 3600) % 24
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return time(hours, minutes, seconds)
    elif isinstance(val, str):
        parts = [int(p) for p in val.split(":")[:3]]
        return time(*parts)
    elif isinstance(val, time):
        return val
    return time(0, 0, 0)

def check_ist_sleep(start_val, end_val):
    if not start_val or not end_val:
        return False
    try:
        start_time = to_time_obj(start_val)
        end_time = to_time_obj(end_val)
        
        ist = pytz.timezone("Asia/Kolkata")
        now = datetime.now(ist).time()
        
        if start_time < end_time:
            return start_time <= now <= end_time
        elif start_time > end_time:
            return now >= start_time or now <= end_time
    except Exception:
        return False
    return False

async def process_account(account, raw_promo_text, active_delay):
    client = TelegramClient(
        StringSession(account["session_string"]),
        account["api_id"],
        account["api_hash"]
    )
    
    clean_text = clean_base_text(raw_promo_text)
    
    try:
        await client.connect()
        if not await client.is_user_authorized():
            print(f"[{account['phone']}] Account not logged in / Session expired.")
            return

        dialog_count = 0
        async for dialog in client.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                dialog_count += 1
                try:
                    unique_tag = generate_unique_ref()
                    message_payload = f"{clean_text}\n\n{unique_tag}"

                    await client.send_message(dialog.id, message_payload)
                    print(f"[{account['phone']}] Sent [{unique_tag}] -> {dialog.name}")
                    
                    # Wait between group posts
                    await asyncio.sleep(active_delay)

                except SlowModeWaitError as e:
                    print(f"[{account['phone']}] Slow mode in {dialog.name}: skipping group.")
                    continue
                except (UserBannedInChannelError, ChatWriteForbiddenError):
                    print(f"[{account['phone']}] No send permission in {dialog.name}: skipping.")
                    continue
                except FloodWaitError as e:
                    print(f"[{account['phone']}] FloodWait limit: Pausing for {e.seconds}s.")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    print(f"[{account['phone']}] Error in {dialog.name}: {e}")
                    continue
                    
        if dialog_count == 0:
            print(f"[{account['phone']}] No groups found! Make sure this account has joined groups.")
            
    except Exception as e:
        print(f"[{account['phone']}] Client Connection Error: {e}")
    finally:
        await client.disconnect()

async def main():
    print("Telegram Continuous Automation Worker ACTIVE...")
    while True:
        try:
            db = get_db()
            with db.cursor() as cursor:
                cursor.execute("SELECT * FROM settings WHERE id = 1")
                settings = cursor.fetchone()
                
                cursor.execute("""
                    SELECT a.*, p.content AS promo_text 
                    FROM accounts a 
                    INNER JOIN promo_messages p ON a.id = p.assigned_account_id 
                    WHERE a.status = 'active'
                """)
                active_jobs = cursor.fetchall()
            db.close()

            if not active_jobs:
                print("No accounts are currently assigned to any promo message. Assign one in dashboard.")
                await asyncio.sleep(15)
                continue

            if settings and check_ist_sleep(settings["sleep_start_ist"], settings["sleep_end_ist"]):
                print("Global IST Sleep window is active. Resting for 60 seconds...")
                await asyncio.sleep(60)
                continue

            tasks = [
                process_account(job, job["promo_text"], int(settings["active_time_sec"]))
                for job in active_jobs
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            rest_interval = int(settings["rest_time_sec"]) if settings else 120
            print(f"Round completed. Resting for {rest_interval}s before next round...")
            await asyncio.sleep(rest_interval)

        except Exception as e:
            print(f"Main loop error: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())