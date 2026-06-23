import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "stargazing.db"

_SITES_SEED = [
    ("Brazos Bend State Park",    29.37,  -95.63,  5, 20,   "Closest dark site to Houston; alligators", 1),
    ("McDonald Observatory area", 30.67, -104.02,  2, 1490, "Best Bortle in TX; 6+ hr drive",           1),
    ("Balmorhea State Park",      30.95, -103.77,  2,  920, "Near McDonald; excellent",                 1),
    ("Sam Houston National Forest", 30.75, -95.50, 5,   90, "Moderate dark sky, closer option",         1),
    ("Enchanted Rock SP",         30.50,  -98.82,  4,  450, "Good Hill Country site",                   1),
]

_WEIGHTS_SEED = [
    ("cloud_cover",    0.35, "Total sky coverage penalty"),
    ("high_cloud",     0.15, "High cirrus penalty (kills transparency even at low total cover)"),
    ("moon",           0.25, "Moon illumination + hours above horizon"),
    ("lifted_index",   0.15, "Atmospheric stability / seeing proxy"),
    ("humidity",       0.10, "Dew risk and sky transparency"),
]

_SETTINGS_SEED = [
    ("forecast_days",          "10",              "Forecast horizon in days (1–16)"),
    ("timezone",               "America/Chicago", "IANA timezone for all forecasts"),
    ("min_score_threshold",    "40",              "Minimum night quality score worth considering (0–100)"),
    ("disq_max_cloud_cover",   "85",              "Hard disqualifier: max avg nighttime cloud cover (%) — nights above this are excluded"),
    ("disq_max_precip_prob",   "40",              "Hard disqualifier: max avg nighttime precipitation probability (%) — nights above this are excluded"),
    ("disq_min_visibility_km", "10",              "Hard disqualifier: min avg nighttime visibility (km) — nights below this are excluded"),
]


def get_connection() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def get_settings() -> dict:
    con = get_connection()
    rows = con.execute("SELECT key, value FROM app_settings").fetchall()
    con.close()
    return dict(rows)


def init_db() -> None:
    con = get_connection()
    cur = con.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS sites (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            lat           REAL    NOT NULL,
            lon           REAL    NOT NULL,
            bortle_class  INTEGER,
            elevation_m   REAL,
            notes         TEXT,
            active        INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS scoring_weights (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            factor        TEXT    NOT NULL UNIQUE,
            weight        REAL    NOT NULL,
            description   TEXT
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key           TEXT    PRIMARY KEY,
            value         TEXT    NOT NULL,
            description   TEXT
        );
    """)

    if cur.execute("SELECT COUNT(*) FROM sites").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO sites (name, lat, lon, bortle_class, elevation_m, notes, active) VALUES (?,?,?,?,?,?,?)",
            _SITES_SEED,
        )

    if cur.execute("SELECT COUNT(*) FROM scoring_weights").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO scoring_weights (factor, weight, description) VALUES (?,?,?)",
            _WEIGHTS_SEED,
        )

    if cur.execute("SELECT COUNT(*) FROM app_settings").fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO app_settings (key, value, description) VALUES (?,?,?)",
            _SETTINGS_SEED,
        )
    else:
        # Insert any settings added after initial setup without touching existing values
        cur.executemany(
            "INSERT OR IGNORE INTO app_settings (key, value, description) VALUES (?,?,?)",
            _SETTINGS_SEED,
        )

    con.commit()
    con.close()
