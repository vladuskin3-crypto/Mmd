import sqlite3
from datetime import datetime

DB_PATH = "bot.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT DEFAULT '',
            balance     REAL DEFAULT 0,
            mts_count   INTEGER DEFAULT 0,
            joined      TEXT
        );

        CREATE TABLE IF NOT EXISTS tickets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            phone       TEXT,
            code        TEXT,
            status      TEXT DEFAULT 'pending',
            created     TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS withdrawals (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  INTEGER,
            amount   REAL,
            created  TEXT
        );
        """)


# ---------- USERS ----------
def get_user(user_id: int, username: str = ""):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users (user_id, username, joined) VALUES (?,?,?)",
                (user_id, username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        elif username and row["username"] != username:
            conn.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
            row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row)


def add_balance(user_id: int, amount: float):
    with get_conn() as conn:
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))


def subtract_balance(user_id: int, amount: float):
    with get_conn() as conn:
        conn.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))


def inc_mts(user_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE users SET mts_count = mts_count + 1 WHERE user_id=?", (user_id,))


def all_users():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM users").fetchall()]


# ---------- TICKETS ----------
def create_ticket(user_id: int, phone: str):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO tickets (user_id, phone, created) VALUES (?,?,?)",
            (user_id, phone, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        return cur.lastrowid


def set_ticket_code(ticket_id: int, code: str):
    with get_conn() as conn:
        conn.execute("UPDATE tickets SET code=? WHERE id=?", (code, ticket_id))


def set_ticket_status(ticket_id: int, status: str):
    with get_conn() as conn:
        conn.execute("UPDATE tickets SET status=? WHERE id=?", (status, ticket_id))


def get_ticket(ticket_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return dict(row) if row else None


# ---------- WITHDRAWALS ----------
def create_withdrawal(user_id: int, amount: float):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO withdrawals (user_id, amount, created) VALUES (?,?,?)",
            (user_id, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )


# ---------- SETTINGS ----------
def set_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )


def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def get_stats():
    with get_conn() as conn:
        users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        total_balance = conn.execute("SELECT COALESCE(SUM(balance),0) s FROM users").fetchone()["s"]
        total_mts = conn.execute("SELECT COALESCE(SUM(mts_count),0) s FROM users").fetchone()["s"]
        return {"users": users, "balance": total_balance, "mts": total_mts}


def init_settings():
    defaults = {
        "btn1": "📱 Сдать MTS ID",
        "btn2": "👤 Профиль",
        "btn3": "🆘 Поддержка",
        "desc1": "Сдать номер MTS ID и получить $10",
        "desc2": "Ваш профиль и баланс",
        "desc3": "Связаться с поддержкой",
        "color1": "",
        "color2": "",
        "color3": "",
        "photo1": "",
        "photo2": "",
        "photo3": "",
        "bot_running": "1",
    }
    for k, v in defaults.items():
        if not get_setting(k):
            set_setting(k, v)
