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
import re
import secrets
from core.db import db

PICKUP_VERSION = "v194-near"
print(f"📍 core/pickup.py жүктөлдү. Версия = {PICKUP_VERSION}")

MAX_POINTS = 12          # бир сапарга эң көп чекит
KEEP_DAYS = 1            # мындан эски жазуулар өчүрүлөт (24 саат)

# ============ 📍 ЖЕРЛЕРДИН КООРДИНАТТАРЫ (v194) ============
# (кеңдик, узундук, түрү). Түрү чекти аныктайт — NEAR_KM.
# Район — анын борбору (мис. Сокулук району → Сокулук айылы).
NEAR_KM = {
    "bishkek": 15,     # Бишкек — чет жактагы конуштары менен
    "osh": 10,         # Ош шаары
    "city": 7,         # башка шаарлар
    "airport": 3,      # аэропорт — жүргүнчү ошол жерде турат
    "district": 15,    # район — борборунан айыл алыс болушу мүмкүн
}

PLACES = {
    # ✈️ аэропорттор
    "манас аэропорту": (43.0613, 74.4776, "airport"),
    "ош аэропорту": (40.6090, 72.7932, "airport"),
    # чоң шаарлар
    "бишкек": (42.8746, 74.5698, "bishkek"),
    "ош": (40.5283, 72.7985, "osh"),
    # шаарлар
    "жалал-абад": (40.9333, 73.0000, "city"),
    "нарын": (41.4287, 75.9911, "city"),
    "каракол": (42.4907, 78.3936, "city"),
    "талас": (42.5228, 72.2427, "city"),
    "баткен": (40.0625, 70.8194, "city"),
    "чолпон-ата": (42.6496, 77.0826, "city"),
    "токмок": (42.8421, 75.3015, "city"),
    "кара-балта": (42.8142, 73.8481, "city"),
    "балыкчы": (42.4600, 76.1870, "city"),
    "кызыл-кыя": (40.2567, 72.1278, "city"),
    "озгон": (40.7667, 73.3000, "city"),
    "кант": (42.8911, 74.8508, "city"),
    "базар-коргон": (41.0375, 72.7458, "city"),
    "кочкор": (42.2150, 75.7528, "city"),
    "токтогул": (41.8722, 72.9406, "city"),
    "кара-суу": (40.7033, 72.8697, "city"),
    "кара-кол": (41.6261, 72.6688, "city"),        # Жалал-Абаддагы Кара-Көл
    "сулукту": (39.9333, 69.5667, "city"),
    "кербен": (41.4950, 71.7550, "city"),
    "майлуу-суу": (41.2650, 72.4500, "city"),
    "таш-комур": (41.3500, 72.2167, "city"),
    "кемин": (42.7860, 75.6920, "city"),
    "ат-башы": (41.1700, 75.8000, "city"),
    "араван": (40.5150, 72.4970, "city"),
    "ноокат": (40.2650, 72.6150, "city"),
    "кара-кулжа": (40.6320, 73.6450, "city"),
    "кадамжай": (40.1290, 71.7220, "city"),
    "сузак": (40.8980, 72.9030, "city"),
    "ала-бука": (41.4020, 71.4500, "city"),
    # райондор — борборунун координаты
    "аламудун району": (42.8920, 74.6330, "district"),
    "жайыл району": (42.8142, 73.8481, "district"),
    "кемин району": (42.7860, 75.6920, "district"),
    "москва району": (42.8300, 74.1080, "district"),
    "панфилов району": (42.8280, 73.6780, "district"),
    "сокулук району": (42.8610, 74.3000, "district"),
    "чуй району": (42.8000, 75.2000, "district"),
    "ысык-ата району": (42.8911, 74.8508, "district"),
    "алай району": (39.9330, 73.4410, "district"),
    "араван району": (40.5150, 72.4970, "district"),
    "кара-кулжа району": (40.6320, 73.6450, "district"),
    "кара-суу району": (40.7033, 72.8697, "district"),
    "ноокат району": (40.2650, 72.6150, "district"),
    "чон-алай району": (39.5540, 72.1880, "district"),
    "озгон району": (40.7667, 73.3000, "district"),
    "аксы району": (41.4950, 71.7550, "district"),
    "ала-бука району": (41.4020, 71.4500, "district"),
    "базар-коргон району": (41.0375, 72.7458, "district"),
    "ноокен району": (41.0700, 72.6400, "district"),
    "сузак району": (40.8980, 72.9030, "district"),
    "тогуз-торо району": (41.4060, 74.0390, "district"),
    "токтогул району": (41.8722, 72.9406, "district"),
    "чаткал району": (41.8560, 71.2390, "district"),
    "баткен району": (40.0625, 70.8194, "district"),
    "кадамжай району": (40.1290, 71.7220, "district"),
    "лейлек району": (39.9910, 69.5290, "district"),
    "ак-талаа району": (41.2440, 74.9340, "district"),
    "ат-башы району": (41.1700, 75.8000, "district"),
    "жумгал району": (41.9300, 74.5100, "district"),
    "кочкор району": (42.2150, 75.7528, "district"),
    "нарын району": (41.4287, 75.9911, "district"),
    "кара-буура району": (42.6200, 71.5900, "district"),
    "бакай-ата району": (42.4100, 71.9600, "district"),
    "манас району": (42.6200, 72.6000, "district"),     # Талас облусу
    "талас району": (42.5228, 72.2427, "district"),
    "ак-суу району": (42.5000, 78.5300, "district"),
    "жети-огуз району": (42.3430, 78.0050, "district"),
    "тон району": (42.1170, 76.9900, "district"),
    "туп району": (42.7270, 78.3630, "district"),
    "ысык-кол району": (42.6496, 77.0826, "district"),
}

# Эски аттар жана кыска жазылыштар (REGIONS тизмесинен)
_ALIAS = {
    "жайыл": "жайыл району", "аламудун": "аламудун району",
    "лейлек": "лейлек району", "раззаков": "лейлек району",
    "чон-алай": "чон-алай району", "алай": "алай району",
    "аксы": "аксы району", "ноокен": "ноокен району",
    "тогуз-торо": "тогуз-торо району", "чаткал": "чаткал району",
    "ак-талаа": "ак-талаа району", "жумгал": "жумгал району",
    "кара-буура": "кара-буура району", "бакай-ата": "бакай-ата району",
    "ак-суу": "ак-суу району", "жети-огуз": "жети-огуз району",
    "тон": "тон району", "туп": "туп району",
}

# Мурунку ат — башка код колдонсо, иштей берсин
CITIES = {k: (v[0], v[1]) for k, v in PLACES.items()}


def _norm(name):
    n = (name or "").lower().replace("ө", "о").replace("ү", "у").replace("ң", "н")
    n = re.sub(r"\(.*?\)", " ", n)            # «Лейлек (Раззаков)»
    return " ".join(n.split())


def place_of(name):
    """Жердин (кеңдик, узундук, түрү) — табылбаса None.

    Алгач толук аты (мис. «манас району» — Талас, «манас
    аэропорту»), анан «шаары» сыяктуу сөзсүз, акырында
    жалпы аттар. Бир тамгалуу ката менен башка жерге кетпеш
    үчүн бөлүгү менен издебейбиз.
    """
    n = _norm(name)
    if not n:
        return None
    if n in PLACES:
        return PLACES[n]
    short = " ".join(w for w in n.split() if w not in ("шаары", "облусу"))
    for k in (short, _ALIAS.get(short, "")):
        if k in PLACES:
            return PLACES[k]
    return None


def city_coord(name):
    p = place_of(name)
    return (p[0], p[1]) if p else None


def near_limit(name):
    """Ушул жерден жүргүнчү чогултууга канча км чейин болот.
    Жер табылбаса None — анда чек коюлбайт."""
    p = place_of(name)
    return NEAR_KM.get(p[2]) if p else None


def check_near(from_city, lat, lon):
    """v194: точка жөнөй турган жердин жанындабы?

    Кайтарат: (туурабы, аралык_км, чек_км).
    Жөнөгөн жердин координаты жок болсо — (True, None, None).
    """
    p = place_of(from_city)
    if not p:
        return True, None, None
    d = km((p[0], p[1]), (float(lat), float(lon)))
    lim = NEAR_KM.get(p[2])
    return (lim is None or d <= lim), d, lim

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

def _merge_duplicates(cur, post_id):
    """v173: бир жарыяга түзүлүп калган ашыкча шилтемелерди бириктирет.

    Эмне үчүн керек: `create()` алгач издеп, таппаса жазат. Эки
    сурам бир убакта келсе (баскычты шарт-шарт эки басканда), экөө
    тең «жок» деп көрүп, экөө тең жазып салат. Ошондо чекиттер
    биринин алдына түшөт, айдоочу экинчисин ачып, бош карта көрөт.

    КАЙСЫСЫ КАЛАТ: чекити эң көп болгону. Себеби ал — жүргүнчүлөр
    ЧЫНДАП КОЛДОНУП ЖАТКАН шилтеме. Аны калтырсак, алардын
    колундагы шилтеме иштей берет; эски-жаңысына карап тандасак,
    жүргүнчүлөргө жаңы шилтеме таратууга туура келмек.
    Чекити теңме-тең болсо — эң эскиси, ошондо тандоо ар дайым
    бирдей чыгат.

    Калгандарынын чекиттери ошого көчөт — бир да чекит жоголбойт.
    """
    # v174: `pickups` таблицасында `id` тилкеси ЖОК — ачкычы `token`.
    # Иреттөөнү `created_at` боюнча кылабыз: ал тилке бар, эски
    # сапарларды тазалоо ошону колдонот.
    cur.execute("SELECT p.token AS token, p.created_at AS ts, "
                "COUNT(pp.id) AS n "
                "FROM pickups p "
                "LEFT JOIN pickup_points pp ON pp.token = p.token "
                "WHERE p.post_id = %s "
                "GROUP BY p.token, p.created_at "
                "ORDER BY n DESC, p.created_at ASC", (post_id,))
    rows = [dict(r) for r in cur.fetchall()]
    if len(rows) < 2:
        return
    keep, extra = rows[0], rows[1:]
    for r in extra:
        cur.execute("UPDATE pickup_points SET token = %s WHERE token = %s",
                    (keep["token"], r["token"]))
    cur.execute("DELETE FROM pickups WHERE token = ANY(%s)",
                ([r["token"] for r in extra],))
    print(f"[pickup] жарыя {post_id}: {len(extra)} ашыкча шилтеме "
          "бириктирилди")


def _safe(conn, cur, what, fn):
    """v175: бир кадамды аткарат, ката болсо жыгылбайт.

    SQL катасынан кийин Postgres транзакцияны «бузулган» деп
    белгилеп коёт — андан кийинки ар бир сурам да ката берет.
    Ошондуктан rollback кылып, ЖАҢЫ курсор кайтарабыз.

    Кайтарат: (ийгиликтүүбү, курсор)
    """
    try:
        fn(cur)
        return True, cur
    except Exception as e:
        print(f"[pickup] {what} аткарылган жок:", e)
        try:
            conn.rollback()
        except Exception:
            pass
        return False, conn.cursor()


def create(post_id, account_id):
    """Сапарга шилтеме түзөт. Бар болсо — ошол эле кайтарылат.

    v175: бириктирүү да, иреттөө да ӨЗ-ӨЗҮНЧӨ корголгон. Экөө тең
    ЖАКШЫРТУУ гана: иштебей калса, журналга жазылат да, карта
    кадимкидей ачыла берет. Мурда бир SQL катасы бүт мүмкүнчүлүктү
    жаап салчу.
    """
    cleanup()
    with db() as conn:
        cur = conn.cursor()

        # 1) Ашыкча шилтемелерди бириктирүү — оңдоо, милдеттүү эмес
        ok, cur = _safe(conn, cur, "бириктирүү",
                        lambda c: _merge_duplicates(c, post_id))
        if ok:
            try:
                conn.commit()
            except Exception as e:
                print("[pickup] бириктирүүнү сактоо:", e)

        # 2) Бар шилтемени алуу.
        #    Чекити эң көп болгонун алабыз — бул жүргүнчүлөр ЧЫНДАП
        #    колдонуп жаткан шилтеме. Ошондуктан бириктирүү иштебей
        #    калса да, айдоочу туура картаны көрөт.
        #    Теңме-тең болсо `token` боюнча — тандоо ар дайым бирдей
        #    чыгат. `created_at` бул жерде керек эмес.
        box = {}

        def _best(c):
            c.execute("SELECT p.token AS token, p.mtoken AS mtoken, "
                      "COUNT(pp.id) AS n "
                      "FROM pickups p "
                      "LEFT JOIN pickup_points pp ON pp.token = p.token "
                      "WHERE p.post_id = %s "
                      "GROUP BY p.token, p.mtoken "
                      "ORDER BY n DESC, p.token ASC LIMIT 1", (post_id,))
            box["row"] = c.fetchone()

        def _plain(c):
            c.execute("SELECT token, mtoken FROM pickups WHERE post_id = %s",
                      (post_id,))
            box["row"] = c.fetchone()

        ok, cur = _safe(conn, cur, "чекити көп шилтемени табуу", _best)
        if not ok:
            ok, cur = _safe(conn, cur, "шилтемени издөө", _plain)

        row = box.get("row")
        if row:
            return row["token"], row["mtoken"]

        # 3) Жок болсо — жаңысын түзөбүз
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
    """Жаңы чекит кошот.

    v171: кошулган чекиттин НОМЕРИН кайтарат. Жүргүнчүнүн браузери
    аны эстеп калат да, кийин ордун тактаганда экинчи чекит кошпой,
    ошол эле жазууну жаңыртат.
    Чектен ашса False кайтарат (мурдагыдай).
    """
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS c FROM pickup_points WHERE token = %s", (token,))
        if cur.fetchone()["c"] >= MAX_POINTS:
            return False
        cur.execute("INSERT INTO pickup_points (token, name, lat, lon) "
                    "VALUES (%s, %s, %s, %s) RETURNING id",
                    (token, (name or "").strip()[:40], float(lat), float(lon)))
        row = cur.fetchone()
        conn.commit()
        return (row or {}).get("id") or True


def move_point(token, point_id, name, lat, lon):
    """v171: бар чекиттин ордун жана атын жаңыртат.

    Табылбаса False кайтарат — айдоочу аны өчүрүп салган болушу
    мүмкүн. Ошондо чакыруучу жак жаңы чекит кошот.
    """
    with db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE pickup_points SET name = %s, lat = %s, lon = %s "
                    "WHERE token = %s AND id = %s",
                    ((name or "").strip()[:40], float(lat), float(lon),
                     token, int(point_id)))
        conn.commit()
        return cur.rowcount > 0


def del_point(token, point_id):
    with db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM pickup_points WHERE token = %s AND id = %s",
                    (token, point_id))
        conn.commit()
        return cur.rowcount > 0


def counts_for_posts(post_ids):
    """v172: ар бир жарыяда канча жүргүнчү ордун белгиледи.

    Бардык жарыя үчүн БИР сурам — «Менин жарыяларым» бетинде
    жарыя канча болсо да, базага бир эле жолу барабыз.

    Кайтарат: {жарыянын_номери: сан}. Нөл болгондору кирбейт,
    ошондуктан калыпта жөн гана бар-жогун текшерсе болот.
    """
    ids = []
    for i in (post_ids or []):
        try:
            ids.append(int(i))
        except (TypeError, ValueError):
            pass
    if not ids:
        return {}
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT p.post_id AS pid, COUNT(pp.id) AS n
                FROM pickups p
                LEFT JOIN pickup_points pp ON pp.token = p.token
                WHERE p.post_id = ANY(%s)
                GROUP BY p.post_id
            """, (ids,))
            return {r["pid"]: r["n"] for r in cur.fetchall() if r["n"]}
    except Exception as e:
        print("[pickup] сандарды эсептөө катасы:", e)
        return {}


def count_for_account(account_id):
    """v172: ушул колдонуучунун БАРДЫК активдүү сапарларындагы
    белгиленген жүргүнчүлөрдүн жалпы саны. Кабинеттеги сан ушул."""
    if not account_id:
        return 0
    try:
        with db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(pp.id) AS n
                FROM pickups p
                JOIN pickup_points pp ON pp.token = p.token
                JOIN posts po ON po.id = p.post_id
                WHERE p.account_id = %s AND po.active = 1
            """, (account_id,))
            row = cur.fetchone()
            return (row or {}).get("n") or 0
    except Exception as e:
        print("[pickup] жалпы сан катасы:", e)
        return 0


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
