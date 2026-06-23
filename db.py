import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_engine: Engine | None = None

_SITES_SEED = [
    ("Brazos Bend State Park",      29.37,  -95.63,  5,   20, "Closest dark site to Houston; alligators", 1),
    ("McDonald Observatory area",   30.67, -104.02,  2, 1490, "Best Bortle in TX; 6+ hr drive",           1),
    ("Balmorhea State Park",        30.95, -103.77,  2,  920, "Near McDonald; excellent",                 1),
    ("Sam Houston National Forest", 30.75,  -95.50,  5,   90, "Moderate dark sky, closer option",         1),
    ("Enchanted Rock SP",           30.50,  -98.82,  4,  450, "Good Hill Country site",                   1),
]

_WEIGHTS_SEED = [
    ("cloud_cover",  0.35, "Total sky coverage penalty"),
    ("high_cloud",   0.15, "High cirrus penalty (kills transparency even at low total cover)"),
    ("moon",         0.25, "Moon illumination + hours above horizon"),
    ("lifted_index", 0.15, "Atmospheric stability / seeing proxy"),
    ("humidity",     0.10, "Dew risk and sky transparency"),
]

_SETTINGS_SEED = [
    ("forecast_days",          "10",              "Forecast horizon in days (1–16)"),
    ("timezone",               "America/Chicago", "IANA timezone for all forecasts"),
    ("min_score_threshold",    "40",              "Minimum night quality score worth considering (0–100)"),
    ("disq_max_cloud_cover",   "85",              "Hard disqualifier: max avg nighttime cloud cover (%)"),
    ("disq_max_precip_prob",   "40",              "Hard disqualifier: max avg nighttime precipitation probability (%)"),
    ("disq_min_visibility_km", "10",              "Hard disqualifier: min avg nighttime visibility (km)"),
]


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError(
                "DATABASE_URL environment variable is not set. "
                "Set it to a PostgreSQL connection string, e.g. "
                "postgresql://user:password@host:5432/dbname"
            )
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def get_connection() -> Engine:
    """Returns the SQLAlchemy engine. Use with pd.read_sql() or engine.connect()."""
    return get_engine()


def get_settings() -> dict:
    with get_engine().connect() as conn:
        rows = conn.execute(text("SELECT key, value FROM app_settings")).fetchall()
    return dict(rows)


def init_db() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sites (
                id            SERIAL PRIMARY KEY,
                name          TEXT    NOT NULL,
                lat           REAL    NOT NULL,
                lon           REAL    NOT NULL,
                bortle_class  INTEGER,
                elevation_m   REAL,
                notes         TEXT,
                active        INTEGER NOT NULL DEFAULT 1
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scoring_weights (
                id          SERIAL PRIMARY KEY,
                factor      TEXT NOT NULL UNIQUE,
                weight      REAL NOT NULL,
                description TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                description TEXT
            )
        """))

        if conn.execute(text("SELECT COUNT(*) FROM sites")).scalar() == 0:
            conn.execute(
                text("INSERT INTO sites (name, lat, lon, bortle_class, elevation_m, notes, active) "
                     "VALUES (:name, :lat, :lon, :bortle, :elev, :notes, :active)"),
                [{"name": r[0], "lat": r[1], "lon": r[2], "bortle": r[3],
                  "elev": r[4], "notes": r[5], "active": r[6]} for r in _SITES_SEED],
            )

        if conn.execute(text("SELECT COUNT(*) FROM scoring_weights")).scalar() == 0:
            conn.execute(
                text("INSERT INTO scoring_weights (factor, weight, description) VALUES (:factor, :weight, :desc)"),
                [{"factor": r[0], "weight": r[1], "desc": r[2]} for r in _WEIGHTS_SEED],
            )

        if conn.execute(text("SELECT COUNT(*) FROM app_settings")).scalar() == 0:
            conn.execute(
                text("INSERT INTO app_settings (key, value, description) VALUES (:key, :value, :desc)"),
                [{"key": r[0], "value": r[1], "desc": r[2]} for r in _SETTINGS_SEED],
            )
        else:
            conn.execute(
                text("INSERT INTO app_settings (key, value, description) VALUES (:key, :value, :desc) "
                     "ON CONFLICT (key) DO NOTHING"),
                [{"key": r[0], "value": r[1], "desc": r[2]} for r in _SETTINGS_SEED],
            )
