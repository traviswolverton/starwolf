import json
import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

_engine: Engine | None = None

def _load_ida_sites() -> list[dict]:
    path = Path(__file__).parent / "dark_sky_sites.json"
    sites = json.loads(path.read_text())
    return [
        {"name": s["name"], "lat": s["lat"], "lon": s["lon"],
         "bortle": s.get("bortle_class"), "elev": s.get("elevation_m"),
         "notes": s.get("notes"), "active": 0, "site_type": "ida_certified"}
        for s in sites
    ]

_SITE_TYPES_SEED = [
    ("ida_certified",   "IDA Certified"),
    ("tx_state_park",   "Texas State Park"),
    ("national_park",   "National Park"),
    ("national_forest", "National Forest"),
    ("observatory",     "Observatory"),
    ("private",         "Private"),
    ("community",       "IDA Dark Sky Community"),
]

_WEIGHTS_SEED = [
    ("cloud_cover",  0.35, "Total sky coverage penalty"),
    ("high_cloud",   0.15, "High cirrus penalty (kills transparency even at low total cover)"),
    ("moon",         0.25, "Moon illumination + hours above horizon"),
    ("lifted_index", 0.15, "Atmospheric stability / seeing proxy"),
    ("humidity",     0.10, "Dew risk and sky transparency"),
]

_NAKED_EYE_WEIGHTS_SEED = [
    ("cloud_cover",  0.40, "Total sky coverage penalty"),
    ("moon",         0.35, "Moon illumination + hours above horizon (dominant for naked eye)"),
    ("high_cloud",   0.10, "High cirrus penalty"),
    ("humidity",     0.10, "Dew risk and sky transparency"),
    ("lifted_index", 0.05, "Atmospheric stability (less critical for naked eye than telescope)"),
]

_SETTINGS_SEED = [
    ("forecast_days",          "10",              "Forecast horizon in days (1–16)"),
    ("timezone",               "America/Chicago", "IANA timezone for all forecasts"),
    ("min_score_threshold",    "40",              "Minimum night quality score worth considering (0–100)"),
    ("disq_max_cloud_cover",   "85",              "Hard disqualifier: max avg nighttime cloud cover (%)"),
    ("disq_max_precip_prob",   "40",              "Hard disqualifier: max avg nighttime precipitation probability (%)"),
    ("disq_min_visibility_km", "10",              "Hard disqualifier: min avg nighttime visibility (km)"),
    ("default_radius_km",      "500",             "Default proximity radius for activating sites on the Planner page (km)"),
    ("ollama_enabled",          "1",               "Enable Ollama-powered AI features (0=disabled, 1=enabled)"),
    ("ollama_url",             "http://localhost:11434/api/generate", "Ollama API endpoint"),
    ("ollama_model",           "llama3.1:8b",     "Ollama model name (run 'ollama list' to see available models)"),
    ("ollama_timeout",         "30",              "Ollama read timeout in seconds (connect always times out after 3s)"),
    ("ollama_summary_max_rows","10",              "Max scored nights to include in the AI summary context"),
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
                active        INTEGER NOT NULL DEFAULT 1,
                site_type     TEXT    CHECK (site_type IN (
                                  'ida_certified', 'tx_state_park', 'national_park',
                                  'national_forest', 'observatory', 'private', 'community'
                              ))
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS site_types (
                code         TEXT PRIMARY KEY,
                display_name TEXT NOT NULL
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
            CREATE TABLE IF NOT EXISTS naked_eye_weights (
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

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS visitors (
                id           SERIAL PRIMARY KEY,
                visited_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ip_hash      TEXT        NOT NULL,
                city         TEXT,
                region       TEXT,
                country      TEXT,
                country_code TEXT,
                lat          REAL,
                lon          REAL
            )
        """))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS visitors_visited_at_idx ON visitors (visited_at)"
        ))

        # Migrate existing installs that predate the site_type column
        conn.execute(text("""
            ALTER TABLE sites ADD COLUMN IF NOT EXISTS site_type TEXT CHECK (site_type IN (
                'ida_certified', 'tx_state_park', 'national_park',
                'national_forest', 'observatory', 'private', 'community'
            ))
        """))
        conn.execute(text(
            "UPDATE sites SET site_type = 'ida_certified' WHERE site_type IS NULL"
        ))

        if conn.execute(text("SELECT COUNT(*) FROM site_types")).scalar() == 0:
            conn.execute(
                text("INSERT INTO site_types (code, display_name) VALUES (:code, :display_name)"),
                [{"code": c, "display_name": d} for c, d in _SITE_TYPES_SEED],
            )

        if conn.execute(text("SELECT COUNT(*) FROM sites")).scalar() == 0:
            conn.execute(
                text("INSERT INTO sites (name, lat, lon, bortle_class, elevation_m, notes, active, site_type) "
                     "VALUES (:name, :lat, :lon, :bortle, :elev, :notes, :active, :site_type)"),
                _load_ida_sites(),
            )

        if conn.execute(text("SELECT COUNT(*) FROM scoring_weights")).scalar() == 0:
            conn.execute(
                text("INSERT INTO scoring_weights (factor, weight, description) VALUES (:factor, :weight, :desc)"),
                [{"factor": r[0], "weight": r[1], "desc": r[2]} for r in _WEIGHTS_SEED],
            )

        if conn.execute(text("SELECT COUNT(*) FROM naked_eye_weights")).scalar() == 0:
            conn.execute(
                text("INSERT INTO naked_eye_weights (factor, weight, description) VALUES (:factor, :weight, :desc)"),
                [{"factor": r[0], "weight": r[1], "desc": r[2]} for r in _NAKED_EYE_WEIGHTS_SEED],
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
