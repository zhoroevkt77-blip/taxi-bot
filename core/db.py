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
import threading
import psycopg2
import psycopg2.extras
import psycopg2.extensions
import psycopg2.pool

DATABASE_URL = os.environ.get("DATABASE_URL")

DB_VERSION = "v157-pool"
print(f"🗄 core/db.py жүктөлдү. Версия = {DB_VERSION}")


# ============ БАЙЛАНЫШ БАСЕЙНИ (v157) ============
# Мурда ар бир сурам үчүн базага ТАПТАКЫР ЖАҢЫ байланыш ачылчу:
# TCP → TLS → пароль текшерүү. Railway'де бул 100-150 мс, ал эми
# бир бет ачылганда андай байланыш бир нече жолу ачылчу.
#
# Эми байланыштар басейнде сакталат: бир жолу ачылып, кайра-кайра
# колдонулат. Сурам 10-20 мс болуп калат.
#
# Байланыш лимити мурдагыдай корголот: басейн эң көп POOL_MAX
# байланыш кармайт, андан ашпайт.

POOL_MIN = int(os.environ.get("DB_POOL_MIN", "1"))
POOL_MAX = int(os.environ.get("DB_POOL_MAX", "6"))

_POOL = None
_POOL_LOCK = threading.Lock()


def _pool():
    """Басейнди биринчи керек болгондо ачат (бир эле жолу)."""
    global _POOL
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = psycopg2.pool.ThreadedConnectionPool(
                    POOL_MIN, POOL_MAX, DATABASE_URL,
                    cursor_factory=psycopg2.extras.RealDictCursor,
                    # Өлүк байланышты эрте табуу үчүн
                    keepalives=1, keepalives_idle=30,
                    keepalives_interval=10, keepalives_count=3,
                    connect_timeout=10)
                print(f"🗄 Байланыш басейни ачылды "
                      f"({POOL_MIN}–{POOL_MAX})")
    return _POOL


class _Pooled:
    """`with db() as conn:` — чыкканда commit/rollback кылып,
    байланышты БАСЕЙНГЕ кайтарат (жаппайт)."""

    __slots__ = ("_conn",)

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        conn, broken = self._conn, False
        try:
            if exc_type is None:
                conn.commit()
            else:
                conn.rollback()
        except Exception:
            broken = True          # бузулган байланыш кайра берилбейт
        try:
            _pool().putconn(conn, close=broken)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
        return False

    def __getattr__(self, name):
        return getattr(self._conn, name)


class _Direct:
    """Басейн иштебей калса — эски жол: ачып, жабабыз."""

    __slots__ = ("_conn",)

    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        except Exception:
            pass
        finally:
            try:
                self._conn.close()
            except Exception:
                pass
        return False

    def __getattr__(self, name):
        return getattr(self._conn, name)


def db():
    """Базага байланыш. `with db() as conn:` менен колдонулат.

    Басейнден алат. Сервер жаап койгон же жарым-жартылай транзакцияда
    калган байланыш кайра берилбейт — тазасы алынат. Басейн иштебей
    калса, эски жол менен түз байланыш ачылат: сайт токтобойт.
    """
    try:
        p = _pool()
    except Exception as e:
        print("[db] басейн ачылган жок:", e)
        p = None

    if p is not None:
        for _ in range(3):
            try:
                conn = p.getconn()
            except Exception as e:
                print("[db] басейнден алуу катасы:", e)
                break
            try:
                if conn.closed:
                    p.putconn(conn, close=True)
                    continue
                if (conn.get_transaction_status()
                        != psycopg2.extensions.TRANSACTION_STATUS_IDLE):
                    conn.rollback()
            except Exception:
                try:
                    p.putconn(conn, close=True)
                except Exception:
                    pass
                continue
            return _Pooled(conn)

    return _Direct(psycopg2.connect(
        DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor))


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
        _websession_tables(cur)
        _webphoto_table(cur)
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


def _webphoto_table(cur):
    """Сайттан жүктөлгөн сүрөттөр — базада сакталат.

    Railway'деги диск убактылуу, ошондуктан сүрөт базага түшөт.
    Каналга чыгарганда Telegram аны /wphoto/<token> аркылуу алат.
    """
    cur.execute("""CREATE TABLE IF NOT EXISTS web_photos (
        token      TEXT PRIMARY KEY,
        mime       TEXT,
        data       BYTEA,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")


def _websession_tables(cur):
    """Сайтка кирүү: убактылуу код жана браузердин сессиясы."""
    cur.execute("""CREATE TABLE IF NOT EXISTS web_logins (
        token      TEXT PRIMARY KEY,
        account_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS web_sessions (
        sid        TEXT PRIMARY KEY,
        account_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_web_sessions_acc "
                "ON web_sessions (account_id)")


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
