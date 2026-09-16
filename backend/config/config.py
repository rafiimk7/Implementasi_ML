import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine

# Auto-load .env dari folder backend/ jika ada.
# Ini memungkinkan script dijalankan langsung tanpa `export` manual.
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "PT_BGI"),
}

PAYDAY_DATE: str = os.getenv("PAYDAY_DATE", "25")
CALENDARIFIC_API_KEY: str = os.getenv("CALENDARIFIC_API_KEY", "")
HOLIDAY_COUNTRY: str = os.getenv("HOLIDAY_COUNTRY", "ID")


def get_db_engine():
    """Membuat koneksi SQLAlchemy ke database MySQL."""
    connection_string = (
        f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    )
    return create_engine(connection_string, pool_pre_ping=True)
    