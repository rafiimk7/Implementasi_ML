"""
Data Preprocessing Script for ATM Prediction
---------------------------------------------
Membaca dataset dari database MySQL (via config/config.py),
melakukan preprocessing + feature engineering,
dan menyimpan hasilnya ke tabel `preprocessing` di database.

PENDEKATAN:
- Sistem menggunakan Business Rule-Based ML
- Target training = jumlah_hari (hasil kalkulasi: ceil(sisa_pagu / ratas_harian))
- Target ini BUKAN ground truth dari refill events, tapi estimasi dari rumus bisnis
- Model ML akan belajar dari pattern ini dan menangkap pola temporal (hari/bulan/kuartal)

OUTPUT:
- Tabel `preprocessing` dengan:
  * Fitur numerik: sisa_pagu, ratas_harian, selisih_lmb
  * Fitur temporal: hari, bulan, tahun, hari_ke, kuartal, cyclic encoding
  * Fitur kalender cerdas: is_weekend, is_payday, is_holiday  ← BARU
  * Target: jumlah_hari (business rule calculation sebagai target training)
"""

import sys
import os
import numpy as np
import pandas as pd
from sqlalchemy import BigInteger, Date, DateTime, Float, Integer, SmallInteger, String

# Tambahkan root project ke sys.path agar config bisa diimport
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config.config import get_db_engine
from calendar_features import add_calendar_flags

# ==========================================================
# KONFIGURASI
# ==========================================================

SOURCE_TABLE = os.getenv("SOURCE_TABLE", "data_2026")  # tabel sumber (bisa di-override via env var)
OUTPUT_TABLE = "preprocessing"  # tabel hasil preprocessing
DT_COL       = "updated"        # kolom datetime utama

# Konfigurasi fitur kalender cerdas
PAYDAY_DATE          = os.getenv("PAYDAY_DATE", "25")           # "25" atau "last_workday"
CALENDARIFIC_API_KEY = os.getenv("CALENDARIFIC_API_KEY", "")    # API key dari calendarific.com
HOLIDAY_COUNTRY      = os.getenv("HOLIDAY_COUNTRY", "ID")       # kode negara ISO-3166

print(f"[CONFIG] SOURCE_TABLE        : {SOURCE_TABLE}")
print(f"[CONFIG] PAYDAY_DATE         : {PAYDAY_DATE}")
print(f"[CONFIG] HOLIDAY_COUNTRY     : {HOLIDAY_COUNTRY}")
print(f"[CONFIG] CALENDARIFIC_API_KEY: {'*SET*' if CALENDARIFIC_API_KEY else '(tidak diset — pakai fallback)'}")

QUERY = f"""
    SELECT
        tid,
        updated,
        lmb1,
        lmb2,
        lmb3,
        lmb4,
        pagu_existing
    FROM {SOURCE_TABLE}
    ORDER BY tid, updated
"""


# ==========================================================
# 1. LOAD DATA DARI DATABASE
# ==========================================================

def load_data_from_db(query: str = QUERY) -> pd.DataFrame:
    """Membaca data mentah dari MySQL."""
    print("Menghubungkan ke database MySQL...")
    try:
        engine = get_db_engine()
        df = pd.read_sql(query, con=engine)
        print(f"Data berhasil dimuat: {len(df)} baris, {len(df.columns)} kolom")
        return df
    except Exception as e:
        print(f"Gagal membaca data dari database: {e}")
        raise


# ==========================================================
# 2. PREPROCESSING
# ==========================================================

def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    """
    Preprocessing + ekstraksi fitur untuk machine learning.
    
    Alur:
    1. Konversi tipe data
    2. Hitung total_lmb & deteksi refill
    3. Hitung selisih_lmb (dengan refill awareness)
    4. Agregasi harian per TID
    5. Hitung ratas_harian & sisa_pagu
    6. Hitung jumlah_hari (business rule target untuk training)
    """

    # ----------------------------------------------------------
    # INFORMASI DATA AWAL
    # ----------------------------------------------------------
    print("\n" + "=" * 60)
    print("INFORMASI DATA")
    print("=" * 60)
    print("Jumlah baris :", len(df))
    print("Jumlah kolom :", len(df.columns))
    print("Shape        :", df.shape)
    print(df.head().to_string())

    # ----------------------------------------------------------
    # KONVERSI TIPE DATA
    # ----------------------------------------------------------
    df[DT_COL] = pd.to_datetime(df[DT_COL], errors="coerce")
    df["tanggal"] = df[DT_COL].dt.date

    kolom_lmb = ["lmb1", "lmb2", "lmb3", "lmb4"]

    df[kolom_lmb] = (
        df[kolom_lmb]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
    )

    df["pagu_existing"] = (
        pd.to_numeric(df["pagu_existing"], errors="coerce")
        .fillna(0)
    )

    # ----------------------------------------------------------
    # HITUNG TOTAL LMB
    # ----------------------------------------------------------
    df["total_lmb"] = df[kolom_lmb].sum(axis=1)

    # ----------------------------------------------------------
    # SORTING & DEDUPLIKASI
    # ----------------------------------------------------------
    df = (
        df
        .sort_values(["tid", "tanggal", DT_COL])
        .drop_duplicates(subset=["tid", DT_COL])
        .reset_index(drop=True)
    )

    # ----------------------------------------------------------
    # HITUNG SELISIH LMB
    # ----------------------------------------------------------
    df["selisih_lmb"] = (
        df
        .groupby(["tid", "tanggal"])["total_lmb"]
        .diff()
        .abs()
        .fillna(0)
        .astype(int)
    )

    print("\n" + "=" * 70)
    print("HASIL SELISIH")
    print("=" * 70)
    print(
        df[
            ["tid", "tanggal", DT_COL,
             "lmb1", "lmb2", "lmb3", "lmb4",
             "total_lmb", "selisih_lmb"]
        ]
        .head(30)
        .to_string()
    )

    # ----------------------------------------------------------
    # AGREGASI PER TID PER TANGGAL
    # ----------------------------------------------------------
    df_harian = (
        df.groupby(["tid", "tanggal"], as_index=False)
          .agg(
              updated=(DT_COL, "last"),
              lmb1=("lmb1", "last"),
              lmb2=("lmb2", "last"),
              lmb3=("lmb3", "last"),
              lmb4=("lmb4", "last"),
              total_lmb=("total_lmb", "last"),
              pagu_existing=("pagu_existing", "last"),
              selisih_lmb=("selisih_lmb", "sum"),  # Total withdrawal per hari
          )
    )

    # ----------------------------------------------------------
    # HITUNG RATA-RATA HARIAN PER TID
    # ----------------------------------------------------------
    rata = (
        df_harian
        .groupby("tid")["selisih_lmb"]
        .mean()
        .reset_index(name="ratas_harian")
    )
    rata["ratas_harian"] = np.ceil(rata["ratas_harian"]).astype(int)

    df_harian = df_harian.merge(rata, on="tid", how="left")

    # ----------------------------------------------------------
    # HITUNG SISA PAGU
    # ----------------------------------------------------------
    df_harian["sisa_pagu"] = (
        df_harian["pagu_existing"] - df_harian["total_lmb"]
    ).clip(lower=0).astype(int)

    # ----------------------------------------------------------
    # TREND FEATURES (historikal per TID)
    # ----------------------------------------------------------
    df_harian = df_harian.sort_values(["tid", "tanggal"]).reset_index(drop=True)

    df_harian["rolling_7d"] = (
        df_harian.groupby("tid")["selisih_lmb"]
        .transform(lambda s: s.shift(1).rolling(window=7, min_periods=1).mean())
    )

    df_harian["rolling_14d"] = (
        df_harian.groupby("tid")["selisih_lmb"]
        .transform(lambda s: s.shift(1).rolling(window=14, min_periods=1).mean())
    )

    df_harian["trend_7d_ratio"] = (
        df_harian["selisih_lmb"] / df_harian["rolling_7d"].replace(0, np.nan)
    ).fillna(1.0)

    df_harian["trend_14d_ratio"] = (
        df_harian["selisih_lmb"] / df_harian["rolling_14d"].replace(0, np.nan)
    ).fillna(1.0)

    # ----------------------------------------------------------
    # HITUNG TARGET TRAINING: jumlah_hari dan tanggal_habis
    # ----------------------------------------------------------
    # Business rule calculation: ceil(sisa_pagu / ratas_harian)
    # Ini digunakan sebagai TARGET untuk training model ML.
    # Meskipun bukan ground truth refill events, model tetap bisa:
    # - Belajar pola temporal (hari/bulan/kuartal)
    # - Menangkap interaksi fitur non-linear
    # - Generalisasi untuk ATM baru
    # ----------------------------------------------------------
    df_harian = df_harian.sort_values(["tid", "tanggal"]).reset_index(drop=True)

    df_harian["jumlah_hari"] = (
        np.ceil(
            df_harian["sisa_pagu"] /
            df_harian["ratas_harian"].replace(0, np.nan)
        )
        .fillna(0)
        .astype(int)
    )

    df_harian["tanggal_habis"] = (
        pd.to_datetime(df_harian[DT_COL]) +
        pd.to_timedelta(df_harian["jumlah_hari"], unit="D")
    ).dt.strftime("%d-%m-%Y")

    return df_harian


# ==========================================================
# 3. FEATURE ENGINEERING
# ==========================================================

def feature_engineering(df: pd.DataFrame, engine=None) -> pd.DataFrame:
    """
    Menambahkan fitur turunan dari kolom datetime:
    - Kalender dasar      : hari, bulan, tahun, hari_ke
    - Kuartal             : kuartal (1–4)
    - Cyclic encoding     : sin/cos untuk hari, bulan, hari_ke
      (agar model menangkap sifat periodik, mis. Des ≈ Jan)
    - Kalender cerdas     : is_weekend, is_payday, is_holiday  ← BARU
      (menangkap pola penarikan di akhir pekan, gajian, libur nasional)

    Args:
        df     : DataFrame hasil preprocessing
        engine : SQLAlchemy engine untuk holiday cache (opsional)
    """
    df[DT_COL] = pd.to_datetime(df[DT_COL])

    # -- Kalender dasar --
    df["hari"]    = df[DT_COL].dt.day
    df["bulan"]   = df[DT_COL].dt.month
    df["tahun"]   = df[DT_COL].dt.year
    df["hari_ke"] = df[DT_COL].dt.dayofyear

    # -- Kuartal --
    df["kuartal"] = df[DT_COL].dt.quarter          # 1 = Jan–Mar, dst.

    # -- Cyclic encoding --
    # hari dalam bulan : periode 31
    df["hari_sin"]    = np.sin(2 * np.pi * df["hari"]    / 31)
    df["hari_cos"]    = np.cos(2 * np.pi * df["hari"]    / 31)

    # bulan dalam tahun : periode 12
    df["bulan_sin"]   = np.sin(2 * np.pi * df["bulan"]   / 12)
    df["bulan_cos"]   = np.cos(2 * np.pi * df["bulan"]   / 12)

    # hari ke dalam tahun : periode 365
    df["hari_ke_sin"] = np.sin(2 * np.pi * df["hari_ke"] / 365)
    df["hari_ke_cos"] = np.cos(2 * np.pi * df["hari_ke"] / 365)

    # -- Fitur kalender cerdas (flag + jarak ke gajian / libur) --
    df = add_calendar_flags(
        df,
        dt_col=DT_COL,
        engine=engine,
        payday_config=PAYDAY_DATE,
        api_key=CALENDARIFIC_API_KEY,
        country=HOLIDAY_COUNTRY,
    )

    # Interaction features: kalender + transaksi
    df["weekend_x_ratas_harian"] = df["is_weekend"] * df["ratas_harian"]
    df["payday_x_sisa_pagu"] = df["is_payday"] * df["sisa_pagu"]
    df["holiday_x_ratas_harian"] = df["is_holiday"] * df["ratas_harian"]

    # Event-trend interaction: feature event + trend historis
    df["weekend_x_trend"] = df["is_weekend"] * df["trend_7d_ratio"]
    df["payday_x_trend"] = df["is_payday"] * df["trend_7d_ratio"]
    df["holiday_x_trend"] = df["is_holiday"] * df["trend_7d_ratio"]

    print(
        f"\nFitur ditambahkan dari '{DT_COL}':\n"
        "  - Kalender dasar : hari, bulan, tahun, hari_ke, kuartal\n"
        "  - Cyclic encoding: hari_sin, hari_cos, bulan_sin, bulan_cos, hari_ke_sin, hari_ke_cos\n"
        "  - Kalender cerdas: is_weekend, is_payday, is_holiday, days_to_payday, days_since_payday, is_near_holiday_3d\n"
        "  - Trend         : rolling_7d, rolling_14d, trend_7d_ratio, trend_14d_ratio\n"
        "  - Interaction   : weekend_x_ratas_harian, payday_x_sisa_pagu, holiday_x_ratas_harian, weekend_x_trend, payday_x_trend, holiday_x_trend\n"
        f"  - is_weekend         : {df['is_weekend'].sum()} hari\n"
        f"  - is_payday          : {df['is_payday'].sum()} hari\n"
        f"  - is_holiday         : {df['is_holiday'].sum()} hari\n"
        f"  - is_near_holiday_3d : {df['is_near_holiday_3d'].sum()} hari"
    )
    return df


# ==========================================================
# 4. TAMPILKAN RINGKASAN
# ==========================================================

def display_summary(df: pd.DataFrame) -> None:
    """Menampilkan ringkasan hasil preprocessing."""
    kolom_tampil = [
        "tid", "tanggal", DT_COL,
        "lmb1", "lmb2", "lmb3", "lmb4",
        "total_lmb", "selisih_lmb",
        "pagu_existing", "ratas_harian", "sisa_pagu",
        "jumlah_hari", "tanggal_habis",
        "hari", "bulan", "tahun", "hari_ke", "kuartal",
        "is_weekend", "is_payday", "is_holiday",
        "days_to_payday", "days_since_payday", "is_near_holiday_3d",
        "rolling_7d", "rolling_14d", "trend_7d_ratio", "trend_14d_ratio",
        "weekend_x_ratas_harian", "payday_x_sisa_pagu", "holiday_x_ratas_harian",
        "weekend_x_trend", "payday_x_trend", "holiday_x_trend",
    ]
    # Hanya tampilkan kolom yang ada
    kolom_ada = [k for k in kolom_tampil if k in df.columns]

    print("\n" + "=" * 70)
    print("INFORMASI DATA SETELAH PREPROCESSING & FEATURE ENGINEERING")
    print("=" * 70)
    print(f"Jumlah data   : {len(df)}")
    print(f"Jumlah kolom  : {len(df.columns)}")

    print("\n📊 DATA PER HARI (20 baris pertama)")
    print(df[kolom_ada].head(20).to_string())

    print("\n📊 DATA PER TID (3 TID pertama)")
    for tid in df["tid"].unique()[:3]:
        print(f"\nTID : {tid}")
        print(df[df["tid"] == tid][kolom_ada].head(10).to_string())


# ==========================================================
# 5. SIMPAN KE DATABASE
# ==========================================================

def save_to_db(df: pd.DataFrame, table_name: str = OUTPUT_TABLE) -> None:
    """Menyimpan hasil preprocessing ke tabel MySQL (replace jika sudah ada)."""
    print(f"\nMenyimpan data ke tabel '{table_name}'...")
    try:
        # ----------------------------------------------------------
        # PASTIKAN TIPE DATA SESUAI SEBELUM SIMPAN
        # ----------------------------------------------------------
        df["tid"]           = df["tid"].astype(str)
        df["tanggal"]       = pd.to_datetime(df["tanggal"]).dt.date
        df[DT_COL]          = pd.to_datetime(df[DT_COL])
        df["tanggal_habis"] = df["tanggal_habis"].astype(str) if "tanggal_habis" in df.columns else None

        for col in ["lmb1", "lmb2", "lmb3", "lmb4", "total_lmb", "pagu_existing"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")

        for col in ["sisa_pagu", "ratas_harian", "selisih_lmb", "jumlah_hari"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")

        for col in ["hari", "bulan", "tahun", "hari_ke", "kuartal"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int16")

        # Cyclic encoding columns (float64)
        for col in ["hari_sin", "hari_cos", "bulan_sin", "bulan_cos", "hari_ke_sin", "hari_ke_cos"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("float64")

        # Fitur kalender cerdas (0/1 → SmallInteger)
        for col in ["is_weekend", "is_payday", "is_holiday", "is_near_holiday_3d"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int16")

        for col in ["days_to_payday", "days_since_payday"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int16")

        for col in [
            "rolling_7d", "rolling_14d", "trend_7d_ratio", "trend_14d_ratio",
            "weekend_x_ratas_harian", "payday_x_sisa_pagu", "holiday_x_ratas_harian",
            "weekend_x_trend", "payday_x_trend", "holiday_x_trend",
        ]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("float64")

        # ----------------------------------------------------------
        # MAPPING DTYPE KE SQLAlchemy TYPE
        # ----------------------------------------------------------
        dtype_map = {
            "tid":           String(50),
            "tanggal":       Date(),
            DT_COL:          DateTime(),
            "tanggal_habis": String(20),
            "lmb1":          BigInteger(),
            "lmb2":          BigInteger(),
            "lmb3":          BigInteger(),
            "lmb4":          BigInteger(),
            "total_lmb":     BigInteger(),
            "pagu_existing": BigInteger(),
            "selisih_lmb":   BigInteger(),
            "sisa_pagu":     BigInteger(),
            "ratas_harian":  Integer(),
            "jumlah_hari":   Integer(),
            "hari":          SmallInteger(),
            "bulan":         SmallInteger(),
            "tahun":         SmallInteger(),
            "hari_ke":       SmallInteger(),
            "kuartal":       SmallInteger(),
            "hari_sin":      Float(),
            "hari_cos":      Float(),
            "bulan_sin":     Float(),
            "bulan_cos":     Float(),
            "hari_ke_sin":   Float(),
            "hari_ke_cos":   Float(),
            "is_weekend":    SmallInteger(),
            "is_payday":     SmallInteger(),
            "is_holiday":    SmallInteger(),
            "days_to_payday": SmallInteger(),
            "days_since_payday": SmallInteger(),
            "is_near_holiday_3d": SmallInteger(),
            "rolling_7d": Float(),
            "rolling_14d": Float(),
            "trend_7d_ratio": Float(),
            "trend_14d_ratio": Float(),
            "weekend_x_ratas_harian": Float(),
            "payday_x_sisa_pagu": Float(),
            "holiday_x_ratas_harian": Float(),
            "weekend_x_trend": Float(),
            "payday_x_trend": Float(),
            "holiday_x_trend": Float(),
        }
        # Hanya sertakan kolom yang benar-benar ada di DataFrame
        dtype_map = {k: v for k, v in dtype_map.items() if k in df.columns}

        engine = get_db_engine()
        df.to_sql(
            name=table_name,
            con=engine,
            if_exists="replace",
            index=False,
            chunksize=1000,
            dtype=dtype_map,
        )
        print(f"✓ Berhasil menyimpan {len(df)} baris ke tabel '{table_name}'")
        print(f"✓ Total kolom: {len(df.columns)}")
    except Exception as e:
        print(f"✗ Gagal menyimpan ke database: {e}")
        raise


# ==========================================================
# MAIN
# ==========================================================

def main():
    print("=" * 70)
    print("DATA PREPROCESSING — FEATURE EXTRACTION ONLY")
    print("=" * 70)

    # 1. Load data mentah dari MySQL
    df = load_data_from_db()

    # 2. Preprocessing (feature engineering tanpa rule-based prediction)
    result = preprocess(df)

    # 3. Feature engineering (fitur turunan datetime + kalender cerdas)
    #    Engine dipass agar holiday_cache bisa diakses dari DB yang sama
    engine = get_db_engine()
    result = feature_engineering(result, engine=engine)

    # 4. Tampilkan ringkasan
    display_summary(result)

    # 5. Simpan ke tabel 'preprocessing' di database
    save_to_db(result)

    print("\n" + "=" * 70)
    print("PREPROCESSING SELESAI")
    print("=" * 70)
    print(f"Total record : {len(result)}")
    print(f"Tabel output : '{OUTPUT_TABLE}'")
    print("\n📌 CATATAN PENTING:")
    print("  ✓ Tabel ini berisi FEATURES + TARGET (jumlah_hari) untuk ML")
    print("  ✓ Target = ceil(sisa_pagu / ratas_harian) → business rule")
    print("  ✓ Fitur baru: is_weekend, is_payday, is_holiday")
    print("  ✓ Jalankan train_model.py untuk training model")
    print("  ✓ Jalankan predict_realtime.py untuk generate prediksi")

    return result


if __name__ == "__main__":
    main()