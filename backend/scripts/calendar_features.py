"""
Calendar Features for ATM Prediction
--------------------------------------
Modul ini menyediakan fitur-fitur kalender cerdas untuk model prediksi ATM:
  - is_weekend  : 1 jika hari Sabtu atau Minggu
  - is_payday   : 1 jika tanggal = hari gajian (default tgl 25, geser ke hari kerja)
  - is_holiday  : 1 jika tanggal = libur nasional Indonesia (via Calendarific API + cache DB)

Konfigurasi (via env vars atau langsung di-pass):
  PAYDAY_DATE           : "25" (default) atau "last_workday"
  CALENDARIFIC_API_KEY  : API key dari https://calendarific.com
  HOLIDAY_COUNTRY       : "ID" (default)

Cara pakai:
  from calendar_features import add_calendar_flags
  df = add_calendar_flags(df, dt_col="updated", engine=engine,
                          payday_config="25",
                          api_key="YOUR_KEY",
                          country="ID")
"""

import calendar
import logging
import os
from datetime import date, timedelta
from typing import List, Optional, Set

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FALLBACK LIBUR NASIONAL (jika API tidak tersedia)
# Update list ini setiap tahun sebagai safety net
# ---------------------------------------------------------------------------
FALLBACK_HOLIDAYS = {
    2026: [
        date(2026, 1, 1),   # New Year's Day
        date(2026, 1, 16),  # Ascension of the Prophet Muhammad
        date(2026, 2, 16),  # Chinese New Year Joint Holiday
        date(2026, 2, 17),  # Chinese New Year's Day
        date(2026, 3, 18),  # Joint Holiday Nyepi
        date(2026, 3, 19),  # Bali's Day of Silence / Nyepi
        date(2026, 3, 20),  # Idul Fitri Joint Holiday
        date(2026, 3, 21),  # Idul Fitri
        date(2026, 3, 22),  # Idul Fitri Holiday
        date(2026, 3, 23),  # Idul Fitri Joint Holiday
        date(2026, 3, 24),  # Idul Fitri Joint Holiday
        date(2026, 4, 3),   # Good Friday
        date(2026, 4, 5),   # Easter Sunday
        date(2026, 5, 1),   # International Labor Day
        date(2026, 5, 14),  # Ascension Day of Jesus Christ
        date(2026, 5, 15),  # Joint Holiday Ascension Day
        date(2026, 5, 27),  # Idul Adha
        date(2026, 5, 28),  # Joint Holiday Idul Adha
        date(2026, 5, 31),  # Waisak Day
        date(2026, 6, 1),   # Pancasila Day
        date(2026, 6, 16),  # Muharram / Islamic New Year
        date(2026, 8, 17),  # Indonesian Independence Day
        date(2026, 8, 25),  # Maulid Nabi Muhammad
        date(2026, 12, 24), # Christmas Eve Joint Holiday
        date(2026, 12, 25), # Christmas Day
    ],
}


# ===========================================================================
# 1. IS_WEEKEND
# ===========================================================================

def is_weekend(d: date) -> bool:
    """
    Return True jika hari adalah Sabtu (5) atau Minggu (6).

    Args:
        d: objek date Python

    Returns:
        bool — True jika weekend
    """
    return d.weekday() >= 5


# ===========================================================================
# 2. GET_PAYDAY_DATE
# ===========================================================================

def get_payday_date(year: int, month: int, payday_config: str = "25") -> date:
    """
    Hitung tanggal gajian untuk bulan tertentu.

    Config yang didukung:
      "last_workday" → hari kerja terakhir bulan itu
      "25"           → tanggal 25 (atau angka lain); jika jatuh di weekend,
                       digeser ke hari Jumat terdekat sebelumnya

    Args:
        year         : tahun (int)
        month        : bulan (int 1-12)
        payday_config: string dari env var PAYDAY_DATE

    Returns:
        date — tanggal gajian yang sudah disesuaikan
    """
    payday_config = (payday_config or "25").strip().lower()

    if payday_config == "last_workday":
        # Mulai dari hari terakhir bulan, mundur sampai ketemu hari kerja
        last_day = calendar.monthrange(year, month)[1]
        d = date(year, month, last_day)
        while d.weekday() >= 5:          # Sabtu=5, Minggu=6
            d -= timedelta(days=1)
        return d

    # Angka tanggal
    try:
        day = int(payday_config)
    except ValueError:
        logger.warning(
            "PAYDAY_DATE '%s' tidak dikenali, fallback ke tanggal 25.",
            payday_config,
        )
        day = 25

    # Pastikan tidak melebihi akhir bulan (misal Feb tidak punya tgl 30)
    last_day = calendar.monthrange(year, month)[1]
    day = min(day, last_day)

    d = date(year, month, day)

    # Geser ke Jumat terdekat jika jatuh di weekend
    if d.weekday() == 5:          # Sabtu → mundur 1 hari ke Jumat
        d -= timedelta(days=1)
    elif d.weekday() == 6:        # Minggu → mundur 2 hari ke Jumat
        d -= timedelta(days=2)

    return d


# ===========================================================================
# 3. IS_PAYDAY
# ===========================================================================

def is_payday(d: date, payday_config: str = "25") -> bool:
    """
    Return True jika tanggal d adalah hari gajian bulan itu.

    Args:
        d            : objek date Python
        payday_config: konfigurasi tanggal gajian (lihat get_payday_date)

    Returns:
        bool
    """
    return d == get_payday_date(d.year, d.month, payday_config)

# ===========================================================================
# 4. GET_HOLIDAYS (dengan caching DB) — akan dilengkapi di Task 2
#    Untuk sekarang hanya fallback ke FALLBACK_HOLIDAYS
# ===========================================================================

def get_holidays(
    year: int,
    engine=None,
    api_key: str = "",
    country: str = "ID",
) -> Set[date]:
    """
    Ambil set tanggal libur nasional untuk tahun tertentu.

    Urutan prioritas:
      1. Cache dari tabel `holiday_cache` di database (jika engine tersedia)
      2. Calendarific API (jika api_key tersedia) → hasil di-cache ke DB
      3. Fallback ke FALLBACK_HOLIDAYS (hardcode)

    Args:
        year    : tahun yang dicari
        engine  : SQLAlchemy engine (opsional)
        api_key : Calendarific API key (opsional)
        country : kode negara ISO-3166 (default "ID")

    Returns:
        set of date
    """
    # -----------------------------------------------------------------------
    # 1. Coba dari cache DB
    # -----------------------------------------------------------------------
    if engine is not None:
        try:
            cached = _load_holidays_from_cache(year, engine)
            if cached:
                logger.debug(
                    "Holiday cache hit untuk tahun %d (%d hari libur).",
                    year, len(cached),
                )
                return cached
        except Exception as exc:
            logger.warning("Gagal baca holiday_cache: %s", exc)

    # -----------------------------------------------------------------------
    # 2. Coba dari Calendarific API
    # -----------------------------------------------------------------------
    if api_key:
        try:
            dates_and_names = _fetch_holidays_with_names(year, api_key, country)
            if dates_and_names:
                holiday_dates = [d for d, _ in dates_and_names]
                holiday_names = [n for _, n in dates_and_names]

                # Simpan ke cache DB jika engine tersedia
                if engine is not None:
                    try:
                        _save_holidays_to_cache(year, holiday_dates, engine, holiday_names)
                    except Exception as exc:
                        logger.warning("Gagal simpan holiday ke cache: %s", exc)

                return set(holiday_dates)
        except Exception as exc:
            logger.warning("Calendarific API gagal: %s — pakai fallback.", exc)

    # -----------------------------------------------------------------------
    # 3. Fallback ke hardcode
    # -----------------------------------------------------------------------
    fallback = FALLBACK_HOLIDAYS.get(year, set())
    logger.info(
        "Menggunakan fallback holidays untuk tahun %d (%d hari libur).",
        year, len(fallback),
    )
    return set(fallback)


# ===========================================================================
# 5. FETCH_HOLIDAYS_FROM_API
# ===========================================================================

# Endpoint Calendarific v2
CALENDARIFIC_URL = "https://calendarific.com/api/v2/holidays"

# Timeout HTTP request (detik)
_API_TIMEOUT = 10


def fetch_holidays_from_api(
    year: int,
    api_key: str,
    country: str = "ID",
) -> List[date]:
    """
    Memanggil Calendarific API untuk mendapatkan daftar libur nasional.

    Endpoint: GET https://calendarific.com/api/v2/holidays
    Docs    : https://calendarific.com/api-documentation

    Args:
        year    : tahun yang dicari (int)
        api_key : Calendarific API key
        country : kode negara ISO-3166 alpha-2 (default "ID")

    Returns:
        list of date — tanggal-tanggal libur nasional

    Raises:
        requests.HTTPError  : jika respons API bukan 200
        ValueError          : jika format respons tidak terduga
        RuntimeError        : jika API mengembalikan error field
    """
    if not api_key:
        raise ValueError("api_key kosong — tidak bisa memanggil Calendarific API.")

    params = {
        "api_key": api_key,
        "country": country,
        "year": year,
        "type": "national",          # hanya libur nasional
    }

    logger.debug("Memanggil Calendarific API: year=%d, country=%s", year, country)

    response = requests.get(CALENDARIFIC_URL, params=params, timeout=_API_TIMEOUT)
    response.raise_for_status()

    payload = response.json()

    # Cek apakah API mengembalikan error
    meta = payload.get("meta", {})
    code = meta.get("code", 200)
    if code != 200:
        error_msg = meta.get("error_type", "Unknown error")
        raise RuntimeError(
            f"Calendarific API error (code={code}): {error_msg}"
        )

    response_data = payload.get("response", {})
    holidays_raw = response_data.get("holidays", [])

    if not isinstance(holidays_raw, list):
        raise ValueError(
            f"Format respons Calendarific tidak terduga: 'holidays' bukan list. "
            f"Isi response: {response_data}"
        )

    holidays: List[date] = []
    for item in holidays_raw:
        try:
            date_info = item["date"]["iso"]          # contoh: "2026-08-17"
            # Ambil hanya 10 karakter pertama (tanggal saja, tanpa waktu)
            d = date.fromisoformat(str(date_info)[:10])
            holidays.append(d)
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skip satu entry holiday karena format tidak valid: %s — %s", item, exc)
            continue

    logger.info(
        "Calendarific API: %d hari libur ditemukan untuk %s tahun %d.",
        len(holidays), country, year,
    )
    return holidays


# ===========================================================================
# 6. HELPER — DB CACHE (internal)
# ===========================================================================

def _fetch_holidays_with_names(
    year: int,
    api_key: str,
    country: str = "ID",
) -> List[tuple]:
    """
    Internal helper — return list of (date, name) dari Calendarific API.
    Dipakai oleh get_holidays() agar bisa simpan nama ke cache DB.
    """
    if not api_key:
        raise ValueError("api_key kosong.")

    params = {
        "api_key": api_key,
        "country": country,
        "year": year,
        "type": "national",
    }

    response = requests.get(CALENDARIFIC_URL, params=params, timeout=_API_TIMEOUT)
    response.raise_for_status()

    payload = response.json()
    meta = payload.get("meta", {})
    code = meta.get("code", 200)
    if code != 200:
        raise RuntimeError(
            f"Calendarific API error (code={code}): {meta.get('error_type', 'Unknown')}"
        )

    holidays_raw = payload.get("response", {}).get("holidays", [])
    result = []
    for item in holidays_raw:
        try:
            date_str = str(item["date"]["iso"])[:10]
            d = date.fromisoformat(date_str)
            name = item.get("name", "")
            result.append((d, name))
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skip entry holiday tidak valid: %s — %s", item, exc)
    return result


def _load_holidays_from_cache(year: int, engine) -> Set[date]:
    """Baca holidays dari tabel holiday_cache untuk tahun tertentu."""
    query = f"SELECT tanggal FROM holiday_cache WHERE tahun = {int(year)}"
    df = pd.read_sql(query, con=engine)
    if df.empty:
        return set()
    return set(pd.to_datetime(df["tanggal"]).dt.date.tolist())


def _save_holidays_to_cache(year: int, holidays: List[date], engine, names: Optional[List[str]] = None) -> None:
    """
    Simpan daftar holidays ke tabel holiday_cache.

    Args:
        year     : tahun (int)
        holidays : list of date
        engine   : SQLAlchemy engine
        names    : opsional, list nama holiday (harus sama panjang dengan holidays)
    """
    from sqlalchemy import text

    if names is None:
        names = [""] * len(holidays)

    rows = [
        {"tanggal": str(d), "tahun": int(year), "nama": n}
        for d, n in zip(holidays, names)
    ]
    df_cache = pd.DataFrame(rows)

    # Buat tabel jika belum ada
    create_sql = """
    CREATE TABLE IF NOT EXISTS holiday_cache (
        id      INT AUTO_INCREMENT PRIMARY KEY,
        tanggal DATE NOT NULL,
        nama    VARCHAR(150) DEFAULT '',
        tahun   SMALLINT NOT NULL,
        UNIQUE KEY uq_holiday (tanggal)
    )
    """
    with engine.connect() as conn:
        conn.execute(text(create_sql))
        conn.commit()

    # Insert row per row agar bisa skip duplikat dengan INSERT IGNORE
    insert_sql = text(
        "INSERT IGNORE INTO holiday_cache (tanggal, nama, tahun) "
        "VALUES (:tanggal, :nama, :tahun)"
    )
    with engine.connect() as conn:
        conn.execute(insert_sql, df_cache.to_dict("records"))
        conn.commit()

    logger.info("Disimpan %d holiday ke holiday_cache untuk tahun %d.", len(holidays), year)


# ===========================================================================
# 7. ADD_CALENDAR_FLAGS  (fungsi utama yang dipanggil dari preprocessing)
# ===========================================================================

def add_calendar_flags(
    df: pd.DataFrame,
    dt_col: str = "updated",
    engine=None,
    payday_config: str = "25",
    api_key: str = "",
    country: str = "ID",
) -> pd.DataFrame:
    """
    Tambahkan feature kalender dan interaction yang lebih informatif:
      - is_weekend : 1 jika Sabtu/Minggu, else 0
      - is_payday  : 1 jika tanggal gajian bulan itu, else 0
      - is_holiday : 1 jika libur nasional, else 0
      - days_to_payday / days_since_payday : jarak ke tanggal gajian
      - is_near_holiday_3d : 1 jika dalam 3 hari sebelum/sesudah libur

    Args:
        df           : DataFrame dengan kolom datetime
        dt_col       : nama kolom datetime (default "updated")
        engine       : SQLAlchemy engine untuk holiday cache
        payday_config: konfigurasi tanggal gajian (default "25")
        api_key      : Calendarific API key
        country      : kode negara ISO-3166

    Returns:
        DataFrame dengan kolom kalender baru
    """
    df = df.copy()

    dt_series = pd.to_datetime(df[dt_col], errors="coerce")
    valid_mask = dt_series.notna()

    # -----------------------------------------------------------------------
    # IS_WEEKEND
    # -----------------------------------------------------------------------
    df["is_weekend"] = 0
    df.loc[valid_mask, "is_weekend"] = (
        dt_series[valid_mask].dt.date.apply(is_weekend).astype(int).values
    )

    # -----------------------------------------------------------------------
    # IS_PAYDAY + DAY DISTANCE TO PAYDAY
    # -----------------------------------------------------------------------
    df["is_payday"] = 0
    df["days_to_payday"] = 0
    df["days_since_payday"] = 0
    
    if valid_mask.any():
        payday_dates = []
        for d in dt_series[valid_mask].dt.date:
            payday_dates.append(get_payday_date(d.year, d.month, payday_config))

        payday_by_date = pd.Series(payday_dates, index=df.index[valid_mask])
        dates_by_row = pd.Series(dt_series[valid_mask].dt.date.values, index=df.index[valid_mask])

        df.loc[valid_mask, "is_payday"] = (
            dates_by_row.apply(lambda d: int(is_payday(d, payday_config))).values
        )

        df.loc[valid_mask, "days_to_payday"] = (
            dates_by_row.apply(lambda d: (get_payday_date(d.year, d.month, payday_config) - d).days).values
        )
        df.loc[valid_mask, "days_since_payday"] = (
            dates_by_row.apply(lambda d: (d - get_payday_date(d.year, d.month, payday_config)).days).values
        )

    # -----------------------------------------------------------------------
    # IS_HOLIDAY + NEAR HOLIDAY WINDOW
    # -----------------------------------------------------------------------
    years = set(dt_series[valid_mask].dt.year.unique())
    holiday_set: Set[date] = set()
    for yr in years:
        holiday_set |= get_holidays(yr, engine=engine, api_key=api_key, country=country)

    df["is_holiday"] = 0
    df["is_near_holiday_3d"] = 0
    if valid_mask.any():
        holiday_list = sorted(holiday_set)
        holiday_window = set()
        for hd in holiday_list:
            holiday_window |= {hd + timedelta(days=i) for i in range(-3, 4)}

        df.loc[valid_mask, "is_holiday"] = (
            dt_series[valid_mask].dt.date
            .apply(lambda d: int(d in holiday_set))
            .values
        )
        df.loc[valid_mask, "is_near_holiday_3d"] = (
            dt_series[valid_mask].dt.date
            .apply(lambda d: int(d in holiday_window))
            .values
        )

    logger.info(
        "Calendar flags ditambahkan: is_weekend=%d, is_payday=%d, is_holiday=%d, days_to_payday_mean=%.2f, is_near_holiday_3d=%d",
        df["is_weekend"].sum(),
        df["is_payday"].sum(),
        df["is_holiday"].sum(),
        df["days_to_payday"].mean() if "days_to_payday" in df.columns else 0,
        df["is_near_holiday_3d"].sum(),
    )

    return df 