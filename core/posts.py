# -*- coding: utf-8 -*-
"""
core/posts.py
=============
Жарыялар (посттор) менен иштөө. db.py тийбейт — ошол эле базаны колдонот.
"""

from datetime import datetime, timedelta
from core.db import db

POST_LIFETIME_HOURS = 24


def create_post(account_id, role, data):
    """Жаңы жарыя сактайт, id кайтарат."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO posts (account_id, role, name, car, from_city, to_city,
                               date_text, time_text, seats, people_count, baggage,
                               price, comment, phone, is_vip)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (account_id, role, data.get("name"), data.get("car"),
              data.get("from_city"), data.get("to_city"), data.get("date_text"),
              data.get("time_text"), data.get("seats"), data.get("people_count"),
              data.get("baggage"), data.get("price"), data.get("comment"),
              data.get("phone"), 1 if data.get("is_vip") else 0))
        post_id = cur.lastrowid
        conn.commit()
        return post_id


def my_posts(account_id, role=None):
    """Колдонуучунун активдүү жарыялары."""
    with db() as conn:
        cur = conn.cursor()
        if role:
            cur.execute("""SELECT * FROM posts WHERE account_id = ? AND role = ?
                           AND active = 1 ORDER BY created_at DESC""",
                        (account_id, role))
        else:
            cur.execute("""SELECT * FROM posts WHERE account_id = ? AND active = 1
                           ORDER BY created_at DESC""", (account_id,))
        return [dict(r) for r in cur.fetchall()]


def deactivate_post(post_id, account_id):
    """Жарыяны өчүрөт (ээси гана)."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE posts SET active = 0 WHERE id = ? AND account_id = ?",
                    (post_id, account_id))
        conn.commit()
        return cur.rowcount > 0


def search_posts(role, from_city=None, to_city=None):
    """Багыт боюнча жарыя издейт. VIP'тер башында чыгат."""
    q = "SELECT * FROM posts WHERE role = ? AND active = 1"
    args = [role]
    if from_city:
        q += " AND from_city = ?"
        args.append(from_city)
    if to_city:
        q += " AND to_city = ?"
        args.append(to_city)
    q += " ORDER BY is_vip DESC, created_at DESC"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(q, args)
        return [dict(r) for r in cur.fetchall()]


def route_counts(role, to_bishkek=True):
    """Маршрут боюнча жарыя саны — издөө менюсу үчүн."""
    with db() as conn:
        cur = conn.cursor()
        if to_bishkek:
            cur.execute("""SELECT from_city AS k, COUNT(*) AS n FROM posts
                           WHERE role = ? AND active = 1 AND to_city = 'Бишкек'
                           GROUP BY from_city""", (role,))
        else:
            cur.execute("""SELECT to_city AS k, COUNT(*) AS n FROM posts
                           WHERE role = ? AND active = 1 AND from_city = 'Бишкек'
                           GROUP BY to_city""", (role,))
        return [dict(r) for r in cur.fetchall()]


def cleanup_expired():
    """24 сааттан ашкан жарыяларды өчүрөт."""
    limit = (datetime.now() - timedelta(hours=POST_LIFETIME_HOURS)).isoformat(" ")
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM posts WHERE active = 1 AND created_at < ?", (limit,))
        ids = [r["id"] for r in cur.fetchall()]
        if ids:
            cur.execute(f"UPDATE posts SET active = 0 WHERE id IN "
                        f"({','.join('?' * len(ids))})", ids)
            conn.commit()
        return ids
def set_channel_msg(post_id, channel_msg_id):
    """Каналдагы билдирүүнүн id'син сактайт — кийин өчүрүү үчүн."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE posts SET channel_msg_id = ? WHERE id = ?",
                    (channel_msg_id, post_id))
        conn.commit()


def get_post(post_id):
    """Бир жарыяны id боюнча кайтарат."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM posts WHERE id = ?", (post_id,))
        row = cur.fetchone()
        return dict(row) if row else None
def search_by_hashtag(frm, to):
    """Хештег боюнча издейт: #Ош_Бишкек → from='Ош%', to='Бишкек%'"""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT * FROM posts WHERE active = 1
                       AND from_city LIKE ? AND to_city LIKE ?
                       ORDER BY is_vip DESC, created_at DESC""",
                    (f"{frm}%", f"{to}%"))
        return [dict(r) for r in cur.fetchall()]
