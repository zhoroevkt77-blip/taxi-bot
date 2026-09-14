# -*- coding: utf-8 -*-
"""
web/admin.py
============
Сайттагы админ панель. Боттогу «/admin» менюсу ошол бойдон калат —
бул анын ордун баспайт, толуктайт: браузерден иштөө ыңгайлуураак.

КИРҮҮ:
    Сырсөз Railway'дин Variables бөлүмүндө: ADMIN_PASSWORD.
    Ал коюлбаса, панель ТАКЫР ачылбайт — кокустан ачык калбашы үчүн.
    Кирүү сессияга жазылат (Flask session, кол тийгис cookie).

БЕШ БӨЛҮМ:
    📊 Статистика  — сандар жана багыттар боюнча бөлүштүрүү
    📋 Жарыялар    — тизме, издөө, чыпка, өчүрүү
    ⚠️ Модерация   — шектүү жарыялар автоматтык бөлүнөт
    👥 Колдонуучулар — бөгөттөө, мөөнөт кошуу, жарыя берүү
    📢 Билдирүү    — баарына кабар
"""

import os
import re
from datetime import datetime, timedelta

from flask import (Blueprint, render_template, request, redirect,
                   session, url_for, flash)

from core import db, posts, admin as core_admin

ADMIN_WEB_VERSION = "v1"
print(f"🎛 web/admin.py жүктөлдү. Версия = {ADMIN_WEB_VERSION}")

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

bp = Blueprint("admin", __name__, url_prefix="/admin")

POST_LIFETIME_HOURS = 24


# ============ КИРҮҮ ============

def _logged_in():
    return bool(session.get("admin_ok"))


def _guard():
    """Кирбеген болсо — кирүү бетине кайтарат."""
    if not ADMIN_PASSWORD:
        return render_template("admin_login.html", no_pass=True), 503
    if not _logged_in():
        return redirect(url_for("admin.login"))
    return None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if not ADMIN_PASSWORD:
        return render_template("admin_login.html", no_pass=True), 503
    err = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_ok"] = True
            session.permanent = True
            return redirect(url_for("admin.panel"))
        err = "Сырсөз туура эмес"
    return render_template("admin_login.html", err=err)


@bp.route("/logout")
def logout():
    session.pop("admin_ok", None)
    return redirect(url_for("admin.login"))


# ============ МААЛЫМАТ ============

def _q(sql, args=(), one=False):
    """Кыска SQL жардамчысы."""
    try:
        with db.db() as conn:
            cur = conn.cursor()
            cur.execute(sql, args)
            if one:
                r = cur.fetchone()
                return dict(r) if r else None
            return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print("[admin] SQL катасы:", e)
        return None if one else []


def _stats():
    day_ago = datetime.now() - timedelta(hours=24)
    total = _q("SELECT COUNT(*) AS n FROM posts", one=True) or {"n": 0}
    active = _q("SELECT COUNT(*) AS n FROM posts WHERE active = 1",
                one=True) or {"n": 0}
    today = _q("SELECT COUNT(*) AS n FROM posts WHERE created_at >= %s",
               (day_ago,), one=True) or {"n": 0}
    views = _q("SELECT COALESCE(SUM(views),0) AS n FROM posts",
               one=True) or {"n": 0}
    users = _q("SELECT COUNT(*) AS n FROM accounts", one=True) or {"n": 0}
    new_u = _q("SELECT COUNT(*) AS n FROM accounts WHERE created_at >= %s",
               (day_ago,), one=True) or {"n": 0}
    banned = _q("SELECT COUNT(*) AS n FROM accounts WHERE banned = 1",
                one=True) or {"n": 0}
    photos = _q("SELECT COUNT(*) AS n FROM posts WHERE active = 1 "
                "AND (photo_id IS NOT NULL OR photo_url IS NOT NULL)",
                one=True) or {"n": 0}

    by_role = _q("SELECT role, COUNT(*) AS n FROM posts WHERE active = 1 "
                 "GROUP BY role")
    by_route = _q("SELECT from_city, to_city, COUNT(*) AS n FROM posts "
                  "WHERE active = 1 GROUP BY from_city, to_city "
                  "ORDER BY n DESC LIMIT 10")

    return {
        "total": total["n"], "active": active["n"], "today": today["n"],
        "expired": total["n"] - active["n"], "views": views["n"],
        "users": users["n"], "new_users": new_u["n"], "banned": banned["n"],
        "photos": photos["n"],
        "suspicious": len(_suspicious()),
        "by_role": {r["role"]: r["n"] for r in by_role},
        "by_route": by_route,
    }


_LINK_RE = re.compile(r"(https?://|t\.me/|wa\.me/|@[A-Za-z0-9_]{4,})", re.I)


def _flags(p):
    """Жарыянын шектүү белгилери. Тизме кайтарат (бош болсо — таза)."""
    out = []

    # 1) Кыргызстандын номери эмес
    d = "".join(ch for ch in str(p.get("phone") or "") if ch.isdigit())
    if not (d.startswith("996") and len(d) == 12):
        out.append("Номер КР эмес")

    # 2) Комментарийде шилтеме же башка аккаунт
    if _LINK_RE.search(str(p.get("comment") or "")):
        out.append("Комментарийде шилтеме")

    # 3) Аты өтө кыска же сандан турат
    name = str(p.get("name") or "").strip()
    if len(name) < 2 or name.isdigit():
        out.append("Аты шектүү")

    # 4) Багыты өзүнө өзү
    if p.get("from_city") and p.get("from_city") == p.get("to_city"):
        out.append("Багыты бирдей")

    return out


def _suspicious():
    """Шектүү активдүү жарыялар."""
    rows = _q("SELECT * FROM posts WHERE active = 1 ORDER BY created_at DESC")
    out = []
    # Бир аккаунттун көп жарыясы — өзүнчө белги
    counts = {}
    for p in rows:
        counts[p["account_id"]] = counts.get(p["account_id"], 0) + 1
    for p in rows:
        fl = _flags(p)
        if counts.get(p["account_id"], 0) > 3:
            fl.append(f"Бир адамдын {counts[p['account_id']]} жарыясы")
        if fl:
            p["flags"] = fl
            out.append(p)
    return out


def _post_list(q="", state="active", role=""):
    sql = "SELECT * FROM posts WHERE 1=1"
    args = []
    if state == "active":
        sql += " AND active = 1"
    elif state == "off":
        sql += " AND active = 0"
    if role:
        sql += " AND role = %s"
        args.append(role)
    if q:
        sql += (" AND (from_city ILIKE %s OR to_city ILIKE %s "
                "OR name ILIKE %s OR phone ILIKE %s)")
        like = f"%{q}%"
        args += [like, like, like, like]
    sql += " ORDER BY created_at DESC LIMIT 200"
    return _q(sql, args)


def _user_list(q=""):
    sql = ("SELECT a.*, "
           "(SELECT COUNT(*) FROM posts p WHERE p.account_id = a.account_id) "
           "AS posts_n "
           "FROM accounts a WHERE 1=1")
    args = []
    if q:
        if q.isdigit():
            sql += " AND (a.account_id = %s OR a.verified_phone ILIKE %s)"
            args += [int(q), f"%{q}%"]
        else:
            sql += " AND (a.first_name ILIKE %s OR a.verified_phone ILIKE %s)"
            args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY a.created_at DESC LIMIT 200"
    return _q(sql, args)


def _ago(ts):
    if not ts:
        return ""
    try:
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        s = (datetime.now() - ts).total_seconds()
    except Exception:
        return ""
    if s < 3600:
        return f"{int(s // 60)} мүн."
    if s < 86400:
        return f"{int(s // 3600)} саат"
    return f"{int(s // 86400)} күн"


# ============ БЕТ ============

@bp.route("/")
def panel():
    g = _guard()
    if g:
        return g

    tab = request.args.get("tab", "stats")
    q = (request.args.get("q") or "").strip()
    state = request.args.get("state", "active")
    role = request.args.get("role", "")

    ctx = {"tab": tab, "q": q, "state": state, "role": role, "ago": _ago}

    if tab == "stats":
        ctx["s"] = _stats()
    elif tab == "posts":
        ctx["rows"] = _post_list(q, state, role)
    elif tab == "mod":
        ctx["rows"] = _suspicious()
    elif tab == "users":
        ctx["rows"] = _user_list(q)

    return render_template("admin.html", **ctx)


# ============ АРАКЕТТЕР ============

@bp.route("/post/<int:pid>/delete", methods=["POST"])
def post_delete(pid):
    if not _logged_in():
        return redirect(url_for("admin.login"))
    p = posts.get_post(pid)
    if p:
        _q("UPDATE posts SET active = 0 WHERE id = %s", (pid,))
        if p.get("channel_msg_id"):
            try:
                from core import channel
                channel.delete(p["channel_msg_id"])
            except Exception as e:
                print("[admin] каналдан өчүрүү катасы:", e)
    return redirect(request.referrer or url_for("admin.panel", tab="posts"))


@bp.route("/user/<int:uid>/<action>", methods=["POST"])
def user_action(uid, action):
    if not _logged_in():
        return redirect(url_for("admin.login"))

    if action == "ban":
        db.set_banned(uid, True)
        core_admin.notify_account(uid, "🚫 Сиз платформада бөгөттөлдүңүз.")
    elif action == "unban":
        db.set_banned(uid, False)
        core_admin.notify_account(
            uid, "✅ Бөгөттөн чыгарылдыңыз. Кайра колдонсоңуз болот.")
    elif action == "grant":
        try:
            days = int(request.form.get("days", "0"))
        except ValueError:
            days = 0
        if days:
            from core import logic
            logic.grant_days(uid, days)
            core_admin.notify_account(
                uid, f"🎁 Сизге {days} күн мөөнөт кошулду. Ак жол!")
    elif action == "posts":
        try:
            n = int(request.form.get("n", "0"))
        except ValueError:
            n = 0
        if n:
            acc = db.get_account(uid) or {}
            db.update_account(uid, free_posts=(acc.get("free_posts") or 0) + n)
            core_admin.notify_account(
                uid, f"🎁 Сизге {n} акысыз жарыя кошулду.")

    return redirect(request.referrer or url_for("admin.panel", tab="users"))


@bp.route("/broadcast", methods=["POST"])
def broadcast():
    if not _logged_in():
        return redirect(url_for("admin.login"))
    text = (request.form.get("text") or "").strip()
    if not text:
        return redirect(url_for("admin.panel", tab="send"))
    sent, failed = core_admin.broadcast(text)
    return render_template("admin.html", tab="send", q="", state="active",
                           role="", ago=_ago, sent=sent, failed=failed)
