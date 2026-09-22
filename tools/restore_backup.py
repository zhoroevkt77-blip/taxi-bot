# -*- coding: utf-8 -*-
"""
tools/restore_backup.py — core/backup.py жасаган zip'ти базага кайтаруу.

КАНТИП (адегенде ТЕСТТИК базада сынаңыз!):
  1. Railway'де жаңы Postgres түзүңүз (же бар базаны колдонуңуз).
  2. Таблицалар түзүлүшү үчүн ботту ошол базага бир жолу иштетиңиз
     (DATABASE_URL'ди жаңы базага буруп, деплой) — бот таблицаларды өзү түзөт.
  3. Termux'та (Postgres сервисинин DATABASE_PUBLIC_URL дареги менен):
        pip install psycopg2-binary
        python tools/restore_backup.py taxi-backup_....zip "postgresql://..."
  4. Скрипт ар бир таблицаны ТАЗАЛАП, zip'теги маалыматты жазат,
     id санагычтарын (sequence) оңдойт.

⚠️ Бардык таблицалардагы учурдагы маалымат ӨЧӨТ. Скрипт «ООБА» деп
   жазмайынча баштабайт.
"""
import csv
import io
import json
import sys
import zipfile

import psycopg2

# Башка таблицалар шилтеме кылган таблицалар биринчи жазылат
FIRST = ["accounts", "platform_identities", "posts"]


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    path, url = sys.argv[1], sys.argv[2]
    z = zipfile.ZipFile(path)
    manifest = json.loads(z.read("manifest.json"))
    print("📦 Көчүрмө:", manifest.get("created_bishkek"))
    for t, n in manifest["tables"].items():
        print(f"   {t}: {n} сап")
    if input("\nБул базадагы маалымат алмаштырылат. Улантуу үчүн ООБА деп жазыңыз: ") != "ООБА":
        sys.exit("Токтотулду.")

    tables = list(manifest["tables"])
    tables.sort(key=lambda t: (FIRST.index(t) if t in FIRST else len(FIRST), t))

    conn = psycopg2.connect(url)
    cur = conn.cursor()
    try:
        cur.execute("SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'")
        existing = {r[0] for r in cur.fetchall()}
        missing = [t for t in tables if t not in existing]
        if missing:
            sys.exit(f"✗ Бул таблицалар базада жок: {missing}\n"
                     f"  Адегенде ботту ушул базага бир жолу иштетиңиз (2-кадам).")

        try:                       # чет ачкыч текшерүүсүн убактылуу өчүрөбүз
            cur.execute("SET session_replication_role = replica")
        except Exception:
            conn.rollback()
            print("ℹ replica режими жок — таблицалар тартиби менен жазылат.")

        cur.execute("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE")
        for t in tables:
            data = z.read(f"{t}.csv").decode("utf-8")
            header = next(csv.reader(io.StringIO(data)), None)
            if not header:
                continue
            cols = ", ".join(f'"{c}"' for c in header)
            cur.copy_expert(f'COPY "{t}" ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true)',
                            io.StringIO(data))
            print(f"✓ {t}")

        # id санагычтары: кийинки жаңы жазуу эски id менен кагылышпасын
        cur.execute("""SELECT table_name, column_name FROM information_schema.columns
                       WHERE table_schema = 'public' AND column_default LIKE 'nextval(%%'""")
        for t, c in cur.fetchall():
            if t in tables:
                cur.execute(f"""SELECT setval(pg_get_serial_sequence('"{t}"', '{c}'),
                                COALESCE((SELECT MAX("{c}") FROM "{t}"), 0) + 1, false)""")
        conn.commit()
        print("\n✅ Калыбына келтирилди.")
    except Exception:
        conn.rollback()
        print("\n✗ Ката — эч нерсе өзгөргөн жок (баары артка кайтарылды).")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
