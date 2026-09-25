# -*- coding: utf-8 -*-
"""
core/pickup.py
===============
«🗺 Жүргүнчүлөрдү чогултуу» — сайт аркылуу.

Айдоочу ботто баскыч басат, бот эки шилтеме берет:
  • жүргүнчүлөргө таштоочу  →  /pickup/<token>
  • өзүнүн картасы          →  /pickup/m/<mtoken>

Жүргүнчү шилтемени ачып, «📍 Мен ушул жердемин» басат — координаты
базага түшөт. Айдоочу өз бетинен чогултуу иретин жана навигатор
шилтемесин алат.

Маалымат 3 күндөн кийин өзү өчөт (cleanup).
"""

import math
import secrets
from core.db import db

PICKUP_VERSION = "v1-web"
print(f"📍 core/pickup.py жүктөлдү. Версия = {PICKUP_VERSION}")

MAX_POINTS = 12          # бир сапарга эң көп чекит
KEEP_DAYS = 1            # мындан эски жазуулар өчүрүлөт (24 саат)

# Багытты аныктоо үчүн шаарлардын болжолдуу координаттары
CITIES = {
    "бишкек": (42.8746, 74.5698), "ош": (40.5283, 72.7985),
    "жалал-абад": (40.9333, 73.0000), "нарын": (41.4287, 75.9911),
    "каракол": (42.4907, 78.3936), "талас": (42.5228, 72.2427),
    "баткен": (40.0625, 70.8194), "чолпон-ата": (42.6496, 77.0826),
    "токмок": (42.8421, 75.3015), "кара-балта": (42.8142, 73.8481),
    "балыкчы": (42.4600, 76.1870), "кызыл-кыя": (40.2567, 72.1278),
    "озгон": (40.7667, 73.3000), "кант": (42.8911, 74.8508),
    "базар-коргон": (41.0375, 72.7458), "кочкор": (42.2150, 75.7528),
    "токтогул": (41.8722, 72.9406), "кара-суу": (40.7033, 72.8697),
    "кара-кол": (42.4907, 78.3936), "сулуктуу": (39.9333, 69.5667),
    "кербен": (41.4667, 71.7500), "май-суу": (41.2500, 72.4167),
}


def city_coord(name):
    n = (name or "").lower().replace("ө", "о").replace("ү", "у").replace("ң", "н")
    for key in sorted(CITIES, key=len, reverse=True):
        if key in n:
            return CITIES[key]
    return None


def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((la2 - la1) / 2) ** 2 +
         math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(h))


def order_points(pts, dest=None):
    """Эң кыска чогултуу иретин табат.

    6 чекитке чейин — бардык варианттар (720 ирет, бат эсептелет).
    Андан көп болсо — «эң жакынын алып жүрүү» ыкмасы.
    """
    if len(pts) < 2:
        return list(pts)
    xy = [(p["lat"], p["lon"]) for p in pts]
    if len(pts) <= 6:
        import itertools
        best, best_len = None, float("inf")
        for perm in itertools.permutations(range(len(pts))):
            d = sum(km(xy[perm[i]], xy[perm[i + 1]]) for i in range(len(perm) - 1))
            if dest:
                d += km(xy[perm[-1]], dest)
            if d < best_len:
                best, best_len = perm, d
        return [pts[i] for i in best]

    left = list(range(len(pts)))
    # Багыт белгилүү болсо — эң алыскысынан баштайбыз
    cur = max(left, key=lambda i: km(xy[i], dest)) if dest else left[0]
    left.remove(cur)
    order = [cur]
    while left:
        nxt = min(left, key=lambda i: km(xy[cur], xy[i]))
        left.remove(nxt)
        order.append(nxt)
        cur = nxt
    return [pts[i] for i in order]


def nav_links(pts, dest=None):
    """Yandex жана Google навигатор шилтемелери.

    Баштапкы чекит берилбейт — навигатор айдоочунун азыркы
    ордунан баштайт.
    """
    ll = [f"{p['lat']:.6f},{p['lon']:.6f}" for p in pts]
    if not ll:
        return {}
    d = f"{dest[0]:.6f},{dest[1]:.6f}" if dest else None
    y = "https://yandex.ru/maps/?rtext=~" + "~".join(ll + ([d] if d else [])) + "&rtt=auto"
    g_dest = d or ll[-1]
    way = ll if d else ll[:-1]
    g = ("https://www.google.com/maps/dir/?api=1&travelmode=driving"
         f"&destination={g_dest}")
    if way:
        g += "&waypoints=" + "%7C".join(way)
    return {"yandex": y, "google": g}


# ============ БАЗА ============

def create(post_id, account_id):
    """Сапарга шилтеме түзөт. Бар болсо — ошол эле кайтарылат."""
    cleanup()
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT token, mtoken FROM pickups WHERE post_id = %s", (post_id,))
        row = cur.fetchone()
        if row:
            return row["token"], row["mtoken"]
        token, mtoken = secrets.token_urlsafe(6), secrets.token_urlsafe(8)
        cur.execute("INSERT INTO pickups (token, mtoken, post_id, account_id) "
                    "VALUES (%s, %s, %s, %s)", (token, mtoken, post_id, account_id))
        conn.commit()
        return token, mtoken


def by_token(token, manager=False):
    col = "mtoken" if manager else "token"
    with db() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM pickups WHERE {col} = %s", (token,))
        return cur.fetchone()


def points(token):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name, lat, lon FROM pickup_points "
                    "WHERE token = %s ORDER BY id", (token,))
        return [dict(r) for r in cur.fetchall()]


def add_point(token, name, lat, lon):
    """Жаңы чекит кошот. Чектен ашса False кайтарат."""
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM pickup_points WHERE token = %s", (token,))
        if cur.fetchone()["c"] >= MAX_POINTS:
            return False
        cur.execute("INSERT INTO pickup_points (token, name, lat, lon) "
                    "VALUES (%s, %s, %s, %s)",
                    (token, (name or "").strip()[:40], float(lat), float(lon)))
        conn.commit()
        return True


def del_point(token, point_id):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM pickup_points WHERE token = %s AND id = %s",
                    (token, point_id))
        conn.commit()
        return cur.rowcount > 0


def cleanup():
    """Эски сапарларды өчүрөт — локациялар узакка сакталбасын."""
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM pickups WHERE created_at < "
                        f"NOW() - INTERVAL '{KEEP_DAYS} days'")
            conn.commit()
    except Exception as e:
        print("[pickup] тазалоо катасы:", e)
