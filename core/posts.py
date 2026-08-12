# -*- coding: utf-8 -*-
"""
core/posts.py  (PostgreSQL варианты)
=====================================
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
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        """, (account_id, role, data.get("name"), data.get("car"),
              data.get("from_city"), data.get("to_city"), data.get("date_text"),
              data.get("time_text"), data.get("seats"), data.get("people_count"),
              data.get("baggage"), data.get("price"), data.get("comment"),
              data.get("phone"), 1 if data.get("is_vip") else 0))
        post_id = cur.fetchone()["id"]
        conn.commit()
        return post_id


def my_posts(account_id, role=None):
    """Колдонуучунун активдүү жарыялары."""
    with db() as conn:
        cur = conn.cursor()
        if role:
            cur.execute("""SELECT * FROM posts WHERE account_id = %s AND role = %s
                           AND active = 1 ORDER BY created_at DESC""",
                        (account_id, role))
        else:
            cur.execute("""SELECT * FROM posts WHERE account_id = %s AND active = 1
                           ORDER BY created_at DESC""", (account_id,))
        return [dict(r) for r in cur.fetchall()]


def deactivate_post(post_id, account_id):
    """Жарыяны өчүрөт (ээси гана)."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE posts SET active = 0 WHERE id = %s AND account_id = %s",
                    (post_id, account_id))
        conn.commit()
        return cur.rowcount > 0


def search_posts(role, from_city=None, to_city=None):
    """Багыт боюнча жарыя издейт. VIP'тер башында чыгат."""
    q = "SELECT * FROM posts WHERE role = %s AND active = 1"
    args = [role]
    if from_city:
        q += " AND from_city = %s"
        args.append(from_city)
    if to_city:
        q += " AND to_city = %s"
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
                           WHERE role = %s AND active = 1 AND to_city = 'Бишкек'
                           GROUP BY from_city""", (role,))
        else:
            cur.execute("""SELECT to_city AS k, COUNT(*) AS n FROM posts
                           WHERE role = %s AND active = 1 AND from_city = 'Бишкек'
                           GROUP BY to_city""", (role,))
        return [dict(r) for r in cur.fetchall()]


def cleanup_expired():
    """24 сааттан ашкан жарыяларды өчүрөт. Өчкөн посттордун тизмесин кайтарат."""
    limit = datetime.now() - timedelta(hours=POST_LIFETIME_HOURS)
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT id, channel_msg_id FROM posts
                       WHERE active = 1 AND created_at < %s""", (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        if rows:
            ids = [r["id"] for r in rows]
            cur.execute("UPDATE posts SET active = 0 WHERE id = ANY(%s)", (ids,))
            conn.commit()
        return rows


def local_route_counts():
    """Бишкекке тиешеси жок бардык маршруттар (район/шаар аралык)."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT from_city, to_city, role, COUNT(*) AS n FROM posts
                       WHERE active = 1
                         AND from_city <> 'Бишкек' AND to_city <> 'Бишкек'
                       GROUP BY from_city, to_city, role
                       ORDER BY n DESC""")
        return [dict(r) for r in cur.fetchall()]


def local_routes_by_oblast(from_cities, to_cities, role=None):
    """Эки облустун райондорунун ортосундагы маршруттар."""
    q = """SELECT from_city, to_city, COUNT(*) AS n FROM posts
           WHERE active = 1
             AND from_city = ANY(%s) AND to_city = ANY(%s)"""
    args = [from_cities, to_cities]
    if role:
        q += " AND role = %s"
        args.append(role)
    q += " GROUP BY from_city, to_city ORDER BY n DESC"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(q, args)
        return [dict(r) for r in cur.fetchall()]


def set_channel_msg(post_id, channel_msg_id):
    """Каналдагы билдирүүнүн id'син сактайт — кийин өчүрүү үчүн."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE posts SET channel_msg_id = %s WHERE id = %s",
                    (channel_msg_id, post_id))
        conn.commit()


def get_post(post_id):
    """Бир жарыяны id боюнча кайтарат."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM posts WHERE id = %s", (post_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def search_by_hashtag(frm, to):
    """Хештег боюнча издейт: #Ош_Бишкек → from='Ош%', to='Бишкек%'"""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT * FROM posts WHERE active = 1
                       AND from_city LIKE %s AND to_city LIKE %s
                       ORDER BY is_vip DESC, created_at DESC""",
                    (f"{frm}%", f"{to}%"))
        return [dict(r) for r in cur.fetchall()]
