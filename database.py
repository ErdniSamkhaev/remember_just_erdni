import sqlite3
from datetime import datetime
from telegram.ext import CallbackContext
import logging
from pytz import timezone, utc


logging.basicConfig(level=logging.INFO)


conn = sqlite3.connect('database.db', check_same_thread=False)
cursor = conn.cursor()


cursor.execute("""
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    remind_time TEXT NOT NULL
);
""")
conn.commit()


cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    has_started BOOLEAN NOT NULL DEFAULT 0
);
""")
conn.commit()


def add_reminder(chat_id, text, remind_time):
    with conn:
        conn.execute("INSERT INTO reminders (chat_id, text, remind_time) VALUES (?, ?, ?);",
                     (chat_id, text, remind_time))


def check_reminders(context: CallbackContext):
    moscow = timezone('Europe/Moscow')
    current_time = datetime.now(utc)
    current_time = current_time.astimezone(moscow)  # Преобразуем к времени Москвы
    current_time_str = current_time.strftime('%Y-%m-%d %H:%M:%S')

    reminders = get_and_delete_reminders(current_time_str)
    for reminder in reminders:
        _, chat_id, text, _ = reminder
        context.bot.send_message(chat_id=chat_id, text=text)


def get_and_delete_reminders(current_time_arg):
    with conn:
        local_cursor = conn.execute("SELECT * FROM reminders WHERE remind_time <= ?", (current_time_arg,))
        rows = local_cursor.fetchall()
        conn.execute("DELETE FROM reminders WHERE remind_time <= ?", (current_time_arg,))
    return rows if rows else []
