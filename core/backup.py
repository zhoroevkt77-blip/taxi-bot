# -*- coding: utf-8 -*-
"""
core/backup.py
==============
Базанын күнүмдүк камдык көчүрмөсү → админдин Telegram'ына.

  • Базадагы БАРДЫК таблицалар (тизме базадан алынат — жаңы таблица
    кошулса, ал да өзү кирет) CSV'ге түшүрүлөт, бир zip'ке топтолот.
  • Zip админдин Telegram'ына файл болуп барат — көчүрмө Railway'ден
    тышкары сакталат.
  • pg_dump керек эмес: psycopg2'нин COPY буйругу менен.
  • Ар күнү саат BACKUP_HOUR'да (Бишкек убактысы) + админ менюсунан кол менен.

Калыбына келтирүү: tools/restore_backup.py (ичинде нускама бар).

ЭСКЕРТҮҮ: файлда колдонуучулардын номерлери бар — аны эч кимге
жибербеңиз, GitHub'га жүктөбөңүз.
"""
import io
import json
import threading
import time
import zipfile
from datetime import datetime, timedelta

import requests

from core import db

BACKUP_VERSION = "v1"
BACKUP_HOUR = 3                         # түнкү саат 03:00, Бишкек
_BISHKEK = timedelta(hours=6)           # UTC+6, жайкы убакыт жок
_TG_LIMIT = 45 * 1024 * 1024            # Telegram бот файлы ≤ 50 МБ
_LOCK = threading.Lock()

print(f"📦 core/backup.py жүктөлдү. Версия = {BACKUP_VERSION}")


def _local_now():
    return datetime.utcnow() + _BISHKEK


def _col(row, key, idx=0):
    """RealDictCursor (dict) да, кадимки cursor (tuple) да иштесин."""
    return row[key] if isinstance(row, dict) else row[idx]


def make_backup():
    """Бардык таблицаларды zip'ке түшүрөт. (zip_bytes, {таблица: саптар}) кайтарат."""
    counts = {}
    buf = io.BytesIO()
    with db.db() as conn, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                    "ORDER BY table_name")
        tables = [_col(r, "table_name") for r in cur.fetchall()]

        cur.execute("SELECT table_name, column_name, data_type, column_default, "
                    "is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' "
                    "ORDER BY table_name, ordinal_position")
        schema = {}
        for r in cur.fetchall():
            schema.setdefault(_col(r, "table_name"), []).append({
                "column": _col(r, "column_name", 1),
                "type": _col(r, "data_type", 2),
                "default": _col(r, "column_default", 3),
                "nullable": _col(r, "is_nullable", 4),
            })

        for t in tables:
            out = io.StringIO()
            cur.copy_expert(f'COPY "{t}" TO STDOUT WITH (FORMAT csv, HEADER true)', out)
            data = out.getvalue()
            cur.execute(f'SELECT count(*) AS n FROM "{t}"')
            counts[t] = int(_col(cur.fetchone(), "n"))
            z.writestr(f"{t}.csv", data)

        z.writestr("schema.json", json.dumps(schema, ensure_ascii=False, indent=1,
                                             default=str))
        z.writestr("manifest.json", json.dumps({
            "created_bishkek": _local_now().strftime("%Y-%m-%d %H:%M"),
            "tables": counts,
            "backup_version": BACKUP_VERSION,
        }, ensure_ascii=False, indent=1))
    return buf.getvalue(), counts


def _admin_chat():
    from core import admin
    return admin._admin_chat_id(), admin.BOT_TOKEN


def send_backup(reason="күнүмдүк"):
    """Көчүрмө жасап, админге жөнөтөт. True — ийгиликтүү."""
    if not _LOCK.acquire(blocking=False):
        print("📦 Көчүрмө мурун эле жасалып жатат — өткөрүлдү.")
        return False
    try:
        chat, token = _admin_chat()
        if not chat or not token:
            print("📦 Көчүрмө: админдин Telegram chat'ы же BOT_TOKEN жок.")
            return False
        try:
            data, counts = make_backup()
        except Exception as e:
            print("📦 Көчүрмө катасы:", e)
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat,
                                "text": f"⚠️ Базанын көчүрмөсү жасалган жок: {e}"},
                          timeout=20)
            return False

        stamp = _local_now().strftime("%Y-%m-%d_%H%M")
        rows = sum(counts.values())
        caption = (f"📦 Базанын көчүрмөсү ({reason})\n"
                   f"🗓 {_local_now():%d.%m.%Y %H:%M} · {len(counts)} таблица · {rows} сап\n"
                   + ", ".join(f"{t}: {n}" for t, n in counts.items())[:800]
                   + "\n\n🔒 Ичинде номерлер бар — эч кимге жибербеңиз.")
        if len(data) > _TG_LIMIT:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text":
                                f"⚠️ Көчүрмө өтө чоң ({len(data) // 1048576} МБ) — "
                                f"Telegram аркылуу жөнөтүлбөйт."}, timeout=20)
            return False
        r = requests.post(f"https://api.telegram.org/bot{token}/sendDocument",
                          data={"chat_id": chat, "caption": caption},
                          files={"document": (f"taxi-backup_{stamp}.zip", data,
                                              "application/zip")},
                          timeout=120)
        ok = bool(r.json().get("ok"))
        print(f"📦 Көчүрмө жөнөтүлдү: {ok}, {len(data) // 1024} КБ, {rows} сап")
        return ok
    except Exception as e:
        print("📦 Көчүрмөнү жөнөтүү катасы:", e)
        return False
    finally:
        _LOCK.release()


def _cleanup_pickups():
    try:
        from core import pickup
        pickup.cleanup()
    except Exception as e:
        print("[backup] tazaloo katasy:", e)


def _loop():
    last_day = None
    while True:
        now = _local_now()
        if now.hour == BACKUP_HOUR and last_day != now.date():
            last_day = now.date()
            send_backup()
            _cleanup_pickups()
        time.sleep(10 * 60)


def start_backup_scheduler():
    t = threading.Thread(target=_loop, daemon=True, name="backup")
    t.start()
    print(f"📦 Күнүмдүк көчүрмө иштетилди (ар күнү {BACKUP_HOUR:02d}:00, Бишкек).")
    return t
