import os
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Auto-load .env dari folder backend/ jika ada
# Ini memungkinkan script dijalankan langsung tanpa `export` manual
_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)  # override=False: env var yang sudah di-set shell tetap menang

# ===========================================================================
# DATABASE CONFIG
# ===========================================================================

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "PT_BGI"),
}

# ===========================================================================
# CALENDAR FEATURES CONFIG
# ===========================================================================

# Tanggal gajian — "25" (default) atau "last_workday"
# Jika tgl 25 jatuh di akhir pekan, otomatis digeser ke hari Jumat sebelumnya.
PAYDAY_DATE: str = os.getenv("PAYDAY_DATE", "25")

# API key dari https://calendarific.com untuk data libur nasional.
# Jika kosong, sistem memakai daftar libur hardcode (FALLBACK_HOLIDAYS).
CALENDARIFIC_API_KEY: str = os.getenv("CALENDARIFIC_API_KEY", "")

# Kode negara ISO-3166 alpha-2 untuk Calendarific API.
HOLIDAY_COUNTRY: str = os.getenv("HOLIDAY_COUNTRY", "ID")


def get_db_engine():
    """Membuat koneksi engine SQLAlchemy ke database MySQL."""
    connection_string = (
        f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
        f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    )
    return create_engine(connection_string, pool_pre_ping=True)


def get_db_session():
    """Mendapatkan session database SQLAlchemy."""
    engine = get_db_engine()
    session_factory = sessionmaker(bind=engine)
    return session_factory()