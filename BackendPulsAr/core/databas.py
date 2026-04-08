"""
Permanent database for products and their positions
SQLite saves the database as a file.
"""

import sqlite3
import json
import os
from datetime import datetime

DB_FIL = "data/pulsar.db"

def get_conn():
    #Opens or creates the database file
    conn = sqlite3.connect(DB_FIL)
    conn.row_factory = sqlite3.Row  # returnerar dict-liknande rader
    return conn

#Skapa tabeller om de inte finns
def initiera_databas():
    conn = get_conn()
    c    = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS produkter (
            id              TEXT PRIMARY KEY,
            visningsnamn    TEXT NOT NULL,
            varumarke       TEXT DEFAULT '',
            kategori        TEXT DEFAULT '',
            taggar          TEXT DEFAULT '[]',
            ocr_alias       TEXT DEFAULT '[]',
            x               REAL DEFAULT 0,
            y               REAL DEFAULT 0,
            z               REAL DEFAULT 2.5,
            status          TEXT DEFAULT 'I lager',
            säkerhet        TEXT DEFAULT 'medium',
            konfidenspoäng  INTEGER DEFAULT 1,
            senast_sedd     TEXT,
            skapad          TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS skanningar (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            produkt_id  TEXT,
            x           REAL,
            y           REAL,
            z           REAL,
            källa       TEXT,  -- 'personal' eller 'kund'
            tidsstämpel TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS flaggor (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            produkt_id  TEXT,
            typ         TEXT,  -- 'saknas' eller 'fel_position'
            tidsstämpel TEXT,
            hanterad    INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    print(f"✅ Databas initierad: {DB_FIL}")


# ─────────────────────────────────────────────
# PRODUKTER
# ─────────────────────────────────────────────

def spara_produkt(produkt: dict, källa: str = "personal"):
    """
    Sparar eller uppdaterar en produkt.
    
    Om produkten redan finns och källa är 'personal':
    → Uppdatera position direkt
    
    Om produkten redan finns och källa är 'kund':
    → Uppdatera inte position, bara konfirmera att den finns
    """
    conn = get_conn()
    c    = conn.cursor()
    nu   = datetime.now().isoformat()

    befintlig = c.execute(
        "SELECT * FROM produkter WHERE id = ?",
        (produkt["id"],)
    ).fetchone()

    if befintlig is None:
        # Ny produkt — spara direkt
        c.execute("""
            INSERT INTO produkter
            (id, visningsnamn, varumarke, kategori, taggar,
             ocr_alias, x, y, z, status, säkerhet,
             konfidenspoäng, senast_sedd, skapad)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (
            produkt["id"],
            produkt.get("visningsnamn", ""),
            produkt.get("varumarke", ""),
            produkt.get("kategori", ""),
            json.dumps(produkt.get("taggar", []), ensure_ascii=False),
            json.dumps(produkt.get("ocr_alias", []), ensure_ascii=False),
            produkt.get("x", 0),
            produkt.get("y", 0),
            produkt.get("z", 2.5),
            produkt.get("status", "I lager"),
            produkt.get("säkerhet", "medium"),
            nu, nu
        ))

    elif källa == "personal":
        # Personal uppdaterar — lita på det direkt
        c.execute("""
            UPDATE produkter SET
                x              = ?,
                y              = ?,
                z              = ?,
                status         = 'I lager',
                säkerhet       = ?,
                konfidenspoäng = konfidenspoäng + 1,
                senast_sedd    = ?
            WHERE id = ?
        """, (
            produkt.get("x", befintlig["x"]),
            produkt.get("y", befintlig["y"]),
            produkt.get("z", befintlig["z"]),
            produkt.get("säkerhet", "medium"),
            nu,
            produkt["id"]
        ))

        # Uppdatera ocr_alias
        gamla_alias = json.loads(befintlig["ocr_alias"])
        nya_alias   = produkt.get("ocr_alias", [])
        alla_alias  = list(set(gamla_alias + nya_alias))
        c.execute(
            "UPDATE produkter SET ocr_alias = ? WHERE id = ?",
            (json.dumps(alla_alias, ensure_ascii=False), produkt["id"])
        )

    else:
        # Kund — uppdatera bara senast_sedd, inte position
        c.execute("""
            UPDATE produkter SET
                senast_sedd = ?
            WHERE id = ?
        """, (nu, produkt["id"]))

    # Logga skanningen
    c.execute("""
        INSERT INTO skanningar (produkt_id, x, y, z, källa, tidsstämpel)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        produkt["id"],
        produkt.get("x", 0),
        produkt.get("y", 0),
        produkt.get("z", 2.5),
        källa, nu
    ))

    conn.commit()
    conn.close()


def hämta_produkt(prod_id: str) -> dict | None:
    """Hämtar en produkt från databasen."""
    conn = get_conn()
    rad  = conn.execute(
        "SELECT * FROM produkter WHERE id = ?", (prod_id,)
    ).fetchone()
    conn.close()

    if rad is None:
        return None
    return _rad_till_dict(rad)


def hämta_alla_produkter() -> list[dict]:
    """Hämtar alla produkter."""
    conn = get_conn()
    rader = conn.execute(
        "SELECT * FROM produkter ORDER BY visningsnamn"
    ).fetchall()
    conn.close()
    return [_rad_till_dict(r) for r in rader]


def ta_bort_produkt(prod_id: str) -> bool:
    """Tar bort en produkt."""
    conn = get_conn()
    conn.execute("DELETE FROM produkter WHERE id = ?", (prod_id,))
    conn.commit()
    conn.close()
    return True


# ─────────────────────────────────────────────
# FLAGGOR
# ─────────────────────────────────────────────

def flagga_saknas(prod_id: str):
    """Kund rapporterar att produkt saknas på angiven position."""
    conn = get_conn()
    nu   = datetime.now().isoformat()

    # Räkna flaggor de senaste 24h
    antal = conn.execute("""
        SELECT COUNT(*) FROM flaggor
        WHERE produkt_id = ?
        AND typ = 'saknas'
        AND hanterad = 0
        AND tidsstämpel > datetime('now', '-1 day')
    """, (prod_id,)).fetchone()[0]

    conn.execute("""
        INSERT INTO flaggor (produkt_id, typ, tidsstämpel)
        VALUES (?, 'saknas', ?)
    """, (prod_id, nu))

    # Om 3+ kunder rapporterat → markera som "Kontrollera"
    if antal >= 2:
        conn.execute("""
            UPDATE produkter SET status = 'Kontrollera'
            WHERE id = ?
        """, (prod_id,))
        print(f"⚠️  {prod_id} flaggad för kontroll — {antal+1} rapporter")

    conn.commit()
    conn.close()


def hämta_flaggor() -> list[dict]:
    """Hämtar alla ohanterade flaggor för personal."""
    conn  = get_conn()
    rader = conn.execute("""
        SELECT f.*, p.visningsnamn
        FROM flaggor f
        JOIN produkter p ON f.produkt_id = p.id
        WHERE f.hanterad = 0
        ORDER BY f.tidsstämpel DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rader]


# ─────────────────────────────────────────────
# HJÄLPFUNKTION
# ─────────────────────────────────────────────

def _rad_till_dict(rad) -> dict:
    """Konverterar en SQLite-rad till dictionary med parsed JSON."""
    d = dict(rad)
    d["taggar"]     = json.loads(d.get("taggar", "[]"))
    d["ocr_alias"]  = json.loads(d.get("ocr_alias", "[]"))
    return d


# Initieras vid import, tabeller skapas om de inte finns
initiera_databas()