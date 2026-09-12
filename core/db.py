# -*- coding: utf-8 -*-
"""
core/db.py  (PostgreSQL варианты)
==================================
Маалымат-база Railway PostgreSQL'де сакталат — DATABASE_URL керек.

Колдонуучу account_id менен идентификацияланат, анткени бир эле
адам Telegram аркылуу да, WhatsApp аркылуу да кире алат, жана
экөө БИР эле аккаунт болушу керек:

  - platform_id    — "tg:123456" же "wa:996700123456"
  - verified_phone — эки платформаны бир аккаунтка байлаган ачкыч

МИГРАЦИЯ ЖӨНҮНДӨ:
    CREATE TABLE IF NOT EXISTS эски таблицага жаңы мамыча кошпойт.
    Ошондуктан _migrate() өзүнчө иштейт: ADD COLUMN IF NOT EXISTS.
    Жаңы мамыча керек болсо, ошол жерге бир сап кошуу жетиштүү.
"""

import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL")

DB_VERSION = "v2-views-photo"
print(f"🗄 core/db.py жүктөлдү. Версия = {DB_VERSION}")


def db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


# Жаңы мамычалар: (таблица, мамыча, түрү)
_NEW_COLUMNS = [
    # Сайттагы «👁 Көрүү» эсептегичи
    ("posts", "views", "INTEGER DEFAULT 0"),
    # Айдоочунун унаасынын сүрөтү (каалоо боюнча)
    #   photo_id  — Telegram'дын file_id'си
    #   photo_url — WhatsApp берген түз шилтеме
    ("posts", "photo_id", "TEXT"),
    ("posts", "photo_url", "TEXT"),
]


def _migrate(cur):
    """Эски базага жаңы мамычаларды кошот. Бар болсо тийбейт."""
    for table, col, coltype in _NEW_COLUMNS:
        try:
            cur.execute(
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}")
        except Exception as e:
            print(f"[db] {table}.{col} кошуу катасы:", e)


def init_db():
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_id     SERIAL PRIMARY KEY,
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
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS platform_identities (
            platform_id  TEXT PRIMARY KEY,
            account_id   INTEGER REFERENCES accounts(account_id) ON DELETE CASCADE,
            platform     TEXT,
            username     TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id             SERIAL PRIMARY KEY,
            account_id     INTEGER REFERENCES accounts(account_id) ON DELETE CASCADE,
            role           TEXT CHECK (role IN ('driver','passenger')),
            name           TEXT, car TEXT, from_city TEXT, to_city TEXT,
            date_text      TEXT, time_text TEXT, seats TEXT, people_count TEXT,
            baggage        TEXT, price TEXT, comment TEXT, phone TEXT,
            is_vip         INTEGER DEFAULT 0,
            active         INTEGER DEFAULT 1,
            channel_msg_id INTEGER,
            views          INTEGER DEFAULT 0,
            photo_id       TEXT,
            photo_url      TEXT,
            created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        _migrate(cur)
        conn.commit()


def get_or_create_account(platform_id, platform, username=None, first_name=None):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT account_id FROM platform_identities WHERE platform_id = %s",
                    (platform_id,))
        row = cur.fetchone()
        if row:
            acc_id = row["account_id"]
        else:
            cur.execute("INSERT INTO accounts (first_name) VALUES (%s) RETURNING account_id",
                        (first_name,))
            acc_id = cur.fetchone()["account_id"]
            cur.execute(
                "INSERT INTO platform_identities (platform_id, account_id, platform, username) "
                "VALUES (%s, %s, %s, %s)",
                (platform_id, acc_id, platform, username))
        conn.commit()
        cur.execute("SELECT * FROM accounts WHERE account_id = %s", (acc_id,))
        return dict(cur.fetchone())


def link_second_platform(existing_account_id, new_platform_id, platform):
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO platform_identities (platform_id, account_id, platform) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (platform_id) DO UPDATE SET account_id = EXCLUDED.account_id",
            (new_platform_id, existing_account_id, platform))
        conn.commit()


def find_account_by_phone(phone):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM accounts WHERE verified_phone = %s", (phone,))
        row = cur.fetchone()
        return dict(row) if row else None


def update_account(account_id, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k} = %s" for k in fields)
    vals = list(fields.values()) + [account_id]
    with db() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE accounts SET {sets} WHERE account_id = %s", vals)
        conn.commit()


def get_account(account_id):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM accounts WHERE account_id = %s", (account_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def platform_id_of(account_id, platform=None):
    """Аккаунттун platform_id'син кайтарат — кабар жиберүү үчүн."""
    with db() as conn:
        cur = conn.cursor()
        if platform:
            cur.execute("SELECT platform_id FROM platform_identities "
                        "WHERE account_id = %s AND platform = %s LIMIT 1",
                        (account_id, platform))
        else:
            cur.execute("SELECT platform_id FROM platform_identities "
                        "WHERE account_id = %s LIMIT 1", (account_id,))
        row = cur.fetchone()
        return row["platform_id"] if row else None


def count_accounts():
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
    q = ("SELECT pi.platform_id FROM platform_identities pi "
         "JOIN accounts a ON a.account_id = pi.account_id")
    if exclude_banned:
        q += " WHERE a.banned = 0"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(q)
        return [r["platform_id"] for r in cur.fetchall()]


def recent_accounts(limit=10):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM accounts ORDER BY created_at DESC LIMIT %s", (limit,))
        return [dict(r) for r in cur.fetchall()]


def set_banned(account_id, banned=True):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE accounts SET banned = %s WHERE account_id = %s",
                    (1 if banned else 0, account_id))
        conn.commit()
        return cur.rowcount > 0
