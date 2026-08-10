# -*- coding: utf-8 -*-
"""
core/db.py  (SQLite варианты)
=============================
Маалымат-база бир файлда сакталат — DATABASE_URL керек эмес.

Колдонуучу account_id менен идентификацияланат, анткени бир эле
адам Telegram аркылуу да, WhatsApp аркылуу да кире алат, жана
экөө БИР эле аккаунт болушу керек:

  - platform_id    — "tg:123456" же "wa:996700123456"
  - verified_phone — эки платформаны бир аккаунтка байлаган ачкыч

ЭСКЕРТҮҮ: Railway сервисти кайра иштеткенде бул файл жоголушу мүмкүн.
Туруктуу сактоо үчүн кийин PostgreSQL'ге өтөбүз — ошондо ушул файлдын
өзүн гана алмаштырабыз, калган код тийбейт.
"""

import os
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "bot.db")


def db():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            verified_phone TEXT UNIQUE,
            first_name     TEXT,
            ref_count      INTEGER DEFAULT 0,
            referred_by    INTEGER,
            gate_bonus     INTEGER DEFAULT 0,
            access_until   TEXT,
            vip_until      TEXT,
            free_posts     INTEGER DEFAULT 0,
            bonus_claimed  INTEGER DEFAULT 0,
            local_credits  INTEGER DEFAULT 0,
            vip_claimed    INTEGER DEFAULT 0,
            lang           TEXT DEFAULT 'ky',
            banned         INTEGER DEFAULT 0,
            bump_credits   INTEGER DEFAULT 0,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS platform_identities (
            platform_id  TEXT PRIMARY KEY,
            account_id   INTEGER,
            platform     TEXT,
            username     TEXT,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id   INTEGER,
            role         TEXT CHECK (role IN ('driver','passenger')),
            name         TEXT, car TEXT, from_city TEXT, to_city TEXT,
            date_text    TEXT, time_text TEXT, seats TEXT, people_count TEXT,
            baggage      TEXT, price TEXT, comment TEXT, phone TEXT,
            is_vip       INTEGER DEFAULT 0,
            active       INTEGER DEFAULT 1,
            channel_msg_id INTEGER,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (account_id) REFERENCES accounts(account_id) ON DELETE CASCADE
        )
        """)
        conn.commit()


def get_or_create_account(platform_id, platform, username=None, first_name=None):
    """platform_id менен аккаунт бар болсо кайтарат, жок болсо жаңы түзөт."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT account_id FROM platform_identities WHERE platform_id = ?",
                    (platform_id,))
        row = cur.fetchone()
        if row:
            acc_id = row["account_id"]
        else:
            cur.execute("INSERT INTO accounts (first_name) VALUES (?)", (first_name,))
            acc_id = cur.lastrowid
            cur.execute(
                "INSERT INTO platform_identities (platform_id, account_id, platform, username) "
                "VALUES (?, ?, ?, ?)",
                (platform_id, acc_id, platform, username))
        conn.commit()
        cur.execute("SELECT * FROM accounts WHERE account_id = ?", (acc_id,))
        return dict(cur.fetchone())


def link_second_platform(existing_account_id, new_platform_id, platform):
    """Телефон боюнча ырастоодон кийин эки ооз бир мээге кошулат."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO platform_identities (platform_id, account_id, platform) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(platform_id) DO UPDATE SET account_id = excluded.account_id",
            (new_platform_id, existing_account_id, platform))
        conn.commit()


def find_account_by_phone(phone):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM accounts WHERE verified_phone = ?", (phone,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_account(account_id, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [account_id]
    with db() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE accounts SET {sets} WHERE account_id = ?", vals)
        conn.commit()


def get_account(account_id):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,))
        row = cur.fetchone()
        return dict(row) if row else None
      def platform_id_of(account_id, platform=None):
    """Аккаунттун platform_id'син кайтарат — кабар жиберүү үчүн керек.
    platform көрсөтүлсө, ошол платформадагысын гана издейт."""
    with db() as conn:
        cur = conn.cursor()
        if platform:
            cur.execute("""SELECT platform_id FROM platform_identities
                           WHERE account_id = ? AND platform = ? LIMIT 1""",
                        (account_id, platform))
        else:
            cur.execute("""SELECT platform_id FROM platform_identities
                           WHERE account_id = ? LIMIT 1""", (account_id,))
        row = cur.fetchone()
        return row["platform_id"] if row else None


def search_by_hashtag(frm, to):
    """Хештег боюнча издейт: #Ош_Бишкек → from='Ош%', to='Бишкек%'
    Ролго карабай баарын кайтарат (айдоочу да, жүргүнчү да)."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT * FROM posts WHERE active = 1
                       AND from_city LIKE ? AND to_city LIKE ?
                       ORDER BY is_vip DESC, created_at DESC""",
                    (f"{frm}%", f"{to}%"))
        return [dict(r) for r in cur.fetchall()]


def count_accounts():
    """Жалпы колдонуучу саны."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM accounts")
        return cur.fetchone()["n"]


def count_banned():
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM accounts WHERE banned = 1")
        return cur.fetchone()["n"]


def all_platform_ids(exclude_banned=True):
    """Жалпы билдирүү үчүн — бардык колдонуучулардын platform_id'си."""
    q = """SELECT pi.platform_id FROM platform_identities pi
           JOIN accounts a ON a.account_id = pi.account_id"""
    if exclude_banned:
        q += " WHERE a.banned = 0"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(q)
        return [r["platform_id"] for r in cur.fetchall()]


def recent_accounts(limit=10):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT * FROM accounts ORDER BY created_at DESC LIMIT ?""",
                    (limit,))
        return [dict(r) for r in cur.fetchall()]


def set_banned(account_id, banned=True):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE accounts SET banned = ? WHERE account_id = ?",
                    (1 if banned else 0, account_id))
        conn.commit()
        return cur.rowcount > 0
