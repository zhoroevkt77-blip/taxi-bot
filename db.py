# -*- coding: utf-8 -*-
"""
core/db.py
==========
Чоң өзгөрүү: колдонуучу эми account_id менен идентификацияланат,
анткени бир эле адам Telegram аркылуу да, WhatsApp аркылуу да
кире алат, жана экөө БИР эле аккаунт болушу керек.

  - platform_id    — "tg:123456" же "wa:996700123456"
  - verified_phone — эки платформаны бир аккаунтка байлаган ачкыч
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")


def db():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    with db() as conn, conn.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_id     SERIAL PRIMARY KEY,
            verified_phone TEXT UNIQUE,
            first_name     TEXT,
            ref_count      INTEGER DEFAULT 0,
            referred_by    INTEGER,
            gate_bonus     BOOLEAN DEFAULT FALSE,
            access_until   TIMESTAMP,
            vip_until      TIMESTAMP,
            free_posts     INTEGER DEFAULT 0,
            bonus_claimed  INTEGER DEFAULT 0,
            local_credits  INTEGER DEFAULT 0,
            vip_claimed    INTEGER DEFAULT 0,
            lang           TEXT DEFAULT 'ky',
            banned         BOOLEAN DEFAULT FALSE,
            bump_credits   INTEGER DEFAULT 0,
            created_at     TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS platform_identities (
            platform_id  TEXT PRIMARY KEY,
            account_id   INTEGER REFERENCES accounts(account_id) ON DELETE CASCADE,
            platform     TEXT,
            username     TEXT,
            created_at   TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS posts (
            id           SERIAL PRIMARY KEY,
            account_id   INTEGER REFERENCES accounts(account_id) ON DELETE CASCADE,
            role         TEXT CHECK (role IN ('driver','passenger')),
            name         TEXT, car TEXT, from_city TEXT, to_city TEXT,
            date_text    TEXT, time_text TEXT, seats TEXT, people_count TEXT,
            baggage      TEXT, price TEXT, comment TEXT, phone TEXT,
            is_vip       BOOLEAN DEFAULT FALSE,
            active       BOOLEAN DEFAULT TRUE,
            channel_msg_id BIGINT,
            created_at   TIMESTAMP DEFAULT NOW()
        );
        """)
        conn.commit()


def get_or_create_account(platform_id, platform, username=None, first_name=None):
    """platform_id менен аккаунт бар болсо кайтарат, жок болсо жаңы түзөт."""
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
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
        return cur.fetchone()


def link_second_platform(existing_account_id, new_platform_id, platform):
    """Телефон боюнча ырастоодон кийин эки ооз бир мээге кошулат."""
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO platform_identities (platform_id, account_id, platform) "
            "VALUES (%s, %s, %s) "
            "ON CONFLICT (platform_id) DO UPDATE SET account_id = EXCLUDED.account_id",
            (new_platform_id, existing_account_id, platform))
        conn.commit()


def find_account_by_phone(phone):
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM accounts WHERE verified_phone = %s", (phone,))
        return cur.fetchone()


def update_account(account_id, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k} = %s" for k in fields)
    vals = list(fields.values()) + [account_id]
    with db() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE accounts SET {sets} WHERE account_id = %s", vals)
        conn.commit()


def get_account(account_id):
    with db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM accounts WHERE account_id = %s", (account_id,))
        return cur.fetchone()
