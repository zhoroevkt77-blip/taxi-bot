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
import psycopg2.extensions

DATABASE_URL = os.environ.get("DATABASE_URL")

DB_VERSION = "v6-pickup"
print(f"🗄 core/db.py жүктөлдү. Версия = {DB_VERSION}")


class _ClosingConnection(psycopg2.extensions.connection):
    """`with db() as conn:` блогунан чыкканда commit/rollback кылып,
    анан байланышты ЖАБАТ. psycopg2 өзү жаппайт — ошондон
    Railway Postgres'тин байланыш лимити акырындап толчу."""

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def db():
    return psycopg2.connect(DATABASE_URL,
                            connection_factory=_ClosingConnection,
                            cursor_factory=psycopg2.extras.RealDictCursor)


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


# posts таблицасынын индекстери (бар болсо тийбейт)
_INDEXES = [
    # Лента: активдүү посттор ролу боюнча, жаңысы биринчи
    "CREATE INDEX IF NOT EXISTS idx_posts_feed ON posts (active, role, created_at DESC)",
    # Тазалоочу: эскирген посттор
    "CREATE INDEX IF NOT EXISTS idx_posts_created ON posts (created_at)",
    # Шаар боюнча издөө
    "CREATE INDEX IF NOT EXISTS idx_posts_from_city ON posts (from_city)",
    # «Менин посторум» — Postgres FK'га өзү индекс койбойт
    "CREATE INDEX IF NOT EXISTS idx_posts_account ON posts (account_id)",
]


def _indexes(cur):
    """Ар бири өз savepoint'инде — бири катуу болсо, транзакция бузулбайт."""
    for sql in _INDEXES:
        cur.execute("SAVEPOINT ix")
        try:
            cur.execute(sql)
            cur.execute("RELEASE SAVEPOINT ix")
        except Exception as e:
            cur.execute("ROLLBACK TO SAVEPOINT ix")
            print("[db] индекс катасы:", e)


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
        _indexes(cur)
        _wa_private_table(cur)
        _pickup_tables(cur)
        _webdraft_table(cur)
        conn.commit()

    # Браузердин кабары үчүн таблица — өзүнчө модулда


def _webdraft_table(cur):
    """Сайттан берилген, бирок номери ырасталбаган жарыялар."""
    cur.execute("""CREATE TABLE IF NOT EXISTS web_drafts (
        token      TEXT PRIMARY KEY,
        role       TEXT,
        data       TEXT,
        status     TEXT DEFAULT 'pending',
        post_id    INTEGER,
        note       TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")


def _pickup_tables(cur):

    """«🗺 Жүргүнчүлөрдү чогултуу» — сайттагы шилтеме жана чекиттер.

    token   — жүргүнчүлөргө берилчү шилтеме
    mtoken  — айдоочунун өз картасы
    Эски жазуулар core/pickup.py'деги cleanup() менен өчүрүлөт.
    """
    cur.execute("""CREATE TABLE IF NOT EXISTS pickups (
        token      TEXT PRIMARY KEY,
        mtoken     TEXT UNIQUE,
        post_id    INTEGER REFERENCES posts(id) ON DELETE CASCADE,
        account_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS pickup_points (
        id         SERIAL PRIMARY KEY,
        token      TEXT REFERENCES pickups(token) ON DELETE CASCADE,
        name       TEXT,
        lat        DOUBLE PRECISION,
        lon        DOUBLE PRECISION,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pickup_points_token "
                "ON pickup_points (token)")


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


# ---- WhatsApp жеке чаттар: бот унчукпай турган чаттар ----

def _wa_private_table(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS wa_private (
                     chat_id TEXT PRIMARY KEY,
                     added_at TIMESTAMP DEFAULT NOW())""")


def wa_private_add(chat_id):
    """Чатты жеке кыл — бот ал жерде жооп бербейт."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""INSERT INTO wa_private (chat_id) VALUES (%s)
                       ON CONFLICT (chat_id) DO NOTHING""", (chat_id,))
        conn.commit()


def wa_private_remove(chat_id):
    """Чатты кайра ботко кайтар."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM wa_private WHERE chat_id = %s", (chat_id,))
        conn.commit()


def wa_is_private(chat_id):
    """Бул чат жекеби?"""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM wa_private WHERE chat_id = %s", (chat_id,))
        return cur.fetchone() is not None
