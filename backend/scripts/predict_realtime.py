#!/usr/bin/env python
"""
Prediksi Realtime ATM
---------------------
Alur:
  1. Ambil data terbaru dari SOURCE_TABLE.
  2. Identifikasi TID yang aktif pada data tersebut.
  3. Jalankan data_preprocessing (full, semua TID) untuk rebuild preprocessing.
  4. Baca 1 baris terbaru per TID dari preprocessing.
  5. Validasi fitur sesuai model.
  6. Load model → predict.
  7. UPSERT ke hasil_prediksi — hanya TID yang dibaca.

Karakteristik:
  - Sumber data       : RAW data_2026 (via preprocessing)
  - Data yang dibaca  : 1 baris terbaru per TID (semua TID dari preprocessing)
  - Butuh preprocessing: Ya (data_preprocessing.main() dijalankan lebih dulu)
  - Skip jika tdk baru: Tidak ada checkpoint.
  - Simpan            : UPSERT hanya TID yang diproses
"""

import json
import sys
import warnings
import os
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import BigInteger, DateTime, Integer, String, text

warnings.filterwarnings("ignore")

# ----------------------------------------------------------
# PATH & KONFIGURASI
# ----------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR   = PROJECT_ROOT / "models"
SCRIPTS_DIR  = Path(__file__).resolve().parent

for p in [str(PROJECT_ROOT), str(SCRIPTS_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from config.config import get_db_engine

SOURCE_TABLE     = os.getenv("SOURCE_TABLE",     "data_2026")
PREPROCESS_TABLE = os.getenv("PREPROCESS_TABLE") or "preprocessing"
PREDICTION_TABLE = os.getenv("PREDICTION_TABLE") or "hasil_prediksi"
DT_COL           = "updated"

PAYDAY_DATE          = os.getenv("PAYDAY_DATE", "25")
CALENDARIFIC_API_KEY = os.getenv("CALENDARIFIC_API_KEY", "")
HOLIDAY_COUNTRY      = os.getenv("HOLIDAY_COUNTRY", "ID")
BUSINESS_RULE_FALLBACK_ENABLED = os.getenv("BUSINESS_RULE_FALLBACK_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def business_rule_days(sisa_pagu, ratas_harian):
    """Hitung estimasi hari habis dengan cast ke int lalu kurangi 1 sebelum simpan.

    Aturan:
      - jika sisa_pagu < ratas_harian -> 0
      - jika cukup, hitung int(sisa_pagu / ratas_harian) lalu kurangi 1
    Ini memastikan tidak ada float dan tanggal_habis mengikuti jumlah_hari final.
    """
    if pd.isna(sisa_pagu) or pd.isna(ratas_harian):
        return 0

    sisa_pagu = float(sisa_pagu)
    ratas_harian = float(ratas_harian)
    if ratas_harian == 0:
        return 0

    if sisa_pagu < ratas_harian:
        return 0

    raw = int(sisa_pagu / ratas_harian)
    return max(raw - 1, 0)


def status_from_hari(hari):
    """Return label status tunggal yang dipakai seluruh layer.

    Aturan konsisten:
      - <= 1 hari  -> 🔴 Kritis
      - 2 sampai 3 hari -> 🟠 Waspada
      - > 3 hari -> 🟢 Aman
    """
    if hari is None or pd.isna(hari):
        return "🟢 Aman"

    h = int(float(hari))
    if h <= 1:
        return "🔴 Kritis"
    if h <= 3:
        return "🟠 Waspada"
    return "🟢 Aman"

print(f"[CONFIG] SOURCE_TABLE        : {SOURCE_TABLE}")
print(f"[CONFIG] PREPROCESS_TABLE    : {PREPROCESS_TABLE}")
print(f"[CONFIG] PAYDAY_DATE         : {PAYDAY_DATE}")
print(f"[CONFIG] CALENDARIFIC_API_KEY: {'*SET*' if CALENDARIFIC_API_KEY else '(tidak diset — pakai fallback)'}")


# ==========================================================
# FITUR MODEL
# ==========================================================

def get_model_feature_list():
    feature_file = MODELS_DIR / "fitur.pkl"
    if feature_file.exists():
        return joblib.load(feature_file)
    try:
        from train_model import FITUR_ML
        return FITUR_ML
    except Exception:
        raise FileNotFoundError(
            "File model belum dibuat. Jalankan train_model.py terlebih dahulu."
        )


FITUR_ML = get_model_feature_list()


# ==========================================================
# 1. CEK DATA RAW
# ==========================================================

def check_new_raw(engine) -> tuple:
    """Ambil TID yang aktif dari SOURCE_TABLE tanpa checkpoint."""
    df_max = pd.read_sql(
        f"SELECT MAX({DT_COL}) AS max_ts FROM {SOURCE_TABLE}", con=engine
    )
    max_ts = pd.to_datetime(df_max["max_ts"].iloc[0]) if not df_max.empty else None

    if max_ts is None or pd.isna(max_ts):
        return None, [], False

    df_tids = pd.read_sql(f"SELECT DISTINCT tid FROM {SOURCE_TABLE}", con=engine)
    tids = df_tids["tid"].tolist()

    if not tids:
        print("[RAW] Tidak ada data di SOURCE_TABLE.")
        return None, [], False

    print(f"[RAW] Total {len(tids)} TID aktif ditemukan. Maks timestamp: {max_ts}")
    return max_ts, tids, True


# ==========================================================
# 2. LOAD DATA DARI preprocessing (1 baris terbaru per TID)
# ==========================================================

def load_latest_from_preprocessing(engine) -> pd.DataFrame:
    """
    Baca 1 baris terbaru per TID dari tabel preprocessing.
    Tabel ini sudah diisi oleh data_preprocessing.main() sebelum fungsi ini dipanggil.
    """
    print("=" * 70)
    print("LOAD DATA TERBARU PER TID DARI preprocessing")
    print("=" * 70)

    query = f"""
        SELECT t.*
        FROM {PREPROCESS_TABLE} t
        INNER JOIN (
            SELECT tid, MAX({DT_COL}) AS max_updated
            FROM {PREPROCESS_TABLE}
            GROUP BY tid
        ) latest
        ON t.tid = latest.tid
        AND t.{DT_COL} = latest.max_updated
    """
    df = pd.read_sql(query, con=engine)
    print(f"Data dimuat : {len(df)} TID, {len(df.columns)} kolom")
    print(f"Timestamp terbaru : {df[DT_COL].max() if not df.empty else 'kosong'}")
    return df


# ==========================================================
# 3. FILTER HANYA TID TERDAMPAK
# ==========================================================

def filter_affected_tids(df: pd.DataFrame, affected_tids: list) -> pd.DataFrame:
    """Ambil hanya baris untuk TID yang punya data RAW baru."""
    df_filtered = df[df["tid"].isin(affected_tids)].copy()
    print(f"\n[Filter] {len(df_filtered)} dari {len(df)} TID akan diprediksi ulang.")
    return df_filtered


# ==========================================================
# 4. VALIDASI FITUR
# ==========================================================

def validate_features(df: pd.DataFrame) -> pd.DataFrame:
    """Validasi ketersediaan fitur dan isi missing value dengan median."""
    if df.empty:
        raise ValueError("Tidak ada data untuk diprediksi.")

    df = df.copy()
    df[DT_COL] = pd.to_datetime(df[DT_COL], errors="coerce")

    missing_cols = [col for col in FITUR_ML if col not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Kolom fitur tidak ditemukan: {missing_cols}\n"
            "Pastikan data_preprocessing.py sudah dijalankan."
        )

    for col in FITUR_ML:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        if df[col].isna().any():
            df[col] = df[col].fillna(df[col].median())

    print(f"\nValidasi fitur : {len(FITUR_ML)} fitur siap | {len(df)} TID")
    return df


# ==========================================================
# 5. LOAD MODEL
# ==========================================================

def load_model():
    """Memuat model, scaler, dan daftar fitur dari disk."""
    model_path  = MODELS_DIR / "model_prediksi_habis.pkl"
    scaler_path = MODELS_DIR / "scaler.pkl"
    fitur_path  = MODELS_DIR / "fitur.pkl"

    for p in [model_path, scaler_path, fitur_path]:
        if not p.exists():
            raise FileNotFoundError(
                f"File model tidak ditemukan: {p}\n"
                "Jalankan train_model.py terlebih dahulu."
            )

    model  = joblib.load(model_path)
    scaler = joblib.load(scaler_path)
    fitur  = joblib.load(fitur_path)
    print(f"\n✅ Model dimuat : {model_path.name} | {len(fitur)} fitur")
    return model, scaler, fitur


# ==========================================================
# 6. PREDIKSI
# ==========================================================

def normalize_prediction_days(df: pd.DataFrame) -> pd.DataFrame:
    """Kurangi prediksi_hari satu hari sebelum dipakai untuk save/output.

    Ini menjaga konsistensi business rule: tanggal_habis dihitung dari hari final
    yang sudah dikurangi 1, bukan dari nilai mentah model.
    """
    df = df.copy()
    if "prediksi_hari" not in df.columns:
        return df

    df["prediksi_hari"] = pd.to_numeric(df["prediksi_hari"], errors="coerce").fillna(0)
    df["prediksi_hari"] = np.maximum(df["prediksi_hari"] - 1, 0).astype(int)
    return df


def assign_threshold(df: pd.DataFrame) -> pd.DataFrame:
    """Tetapkan label status berdasarkan prediksi_hari.

    Aturan status final:
      - <= 1 hari  -> Kritis
      - 2 sampai 3 hari -> Waspada
      - > 3 hari -> Aman
    """
    df = df.copy()
    df["prediksi_hari"] = pd.to_numeric(df["prediksi_hari"], errors="coerce").fillna(0)
    df["threshold"] = df["prediksi_hari"].apply(status_from_hari)
    return df


def apply_business_rule_fallback(df: pd.DataFrame) -> pd.DataFrame:
    """
    Jika business rule fallback dinyalakan secara eksplisit, ganti prediksi dengan
    business rule jika menyimpang >50%. Secara default fallback dimatikan agar
    model penuh tetap dipakai.

    Business rule:
      sisa_pagu < ratas_harian -> 0 hari (habis hari ini)
      selainnya                -> int(sisa_pagu / ratas_harian) - 1
    """
    df = df.copy()

    if not BUSINESS_RULE_FALLBACK_ENABLED:
        print("  ℹ️  Business rule fallback OFF — memakai full model")
        return assign_threshold(df)

    _raw = (
        (df["sisa_pagu"] / df["ratas_harian"].replace(0, np.nan))
        .fillna(0)
        .astype(float)
        .astype(int)
    )
    df["business_rule_hari"] = np.where(
        df["sisa_pagu"] < df["ratas_harian"], 0, np.maximum(_raw - 1, 0)
    )

    if "prediksi_hari" in df.columns:
        diff        = np.abs(df["prediksi_hari"] - df["business_rule_hari"])
        denominator = df["business_rule_hari"].replace(0, 1)
        diff_pct    = (diff / denominator) * 100
        use_rule    = diff_pct > 50

        if use_rule.any():
            print(f"  ⚠️  {use_rule.sum()} TID menggunakan business rule fallback")
            df.loc[use_rule, "prediksi_hari"] = df.loc[use_rule, "business_rule_hari"]
            df.loc[use_rule, "tanggal_habis"] = (
                pd.to_datetime(df.loc[use_rule, DT_COL]) +
                pd.to_timedelta(df.loc[use_rule, "business_rule_hari"], unit="D")
            ).dt.strftime("%d-%m-%Y")

    df = assign_threshold(df)
    return df


def predict(df: pd.DataFrame, model, scaler, fitur: list) -> pd.DataFrame:
    """Jalankan prediksi jumlah_hari dan hitung tanggal_habis."""
    print("\n" + "=" * 70)
    print("PREDIKSI")
    print("=" * 70)

    fitur_kurang = [f for f in fitur if f not in df.columns]
    if fitur_kurang:
        raise ValueError(f"Kolom fitur tidak tersedia: {fitur_kurang}")

    X = df[fitur].copy()
    for col in fitur:
        if X[col].isna().any():
            X[col] = X[col].fillna(X[col].median() if len(X) > 0 else 0)

    X_scaled      = scaler.transform(X)
    prediksi_hari = np.maximum(np.ceil(model.predict(X_scaled)).astype(int), 0)

    df = df.copy()
    df["prediksi_hari"] = prediksi_hari
    df = normalize_prediction_days(df)
    df["tanggal_habis"] = (
        pd.to_datetime(df[DT_COL]) +
        pd.to_timedelta(df["prediksi_hari"], unit="D")
    ).dt.strftime("%d-%m-%Y")
    df["prediksi_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df = assign_threshold(df)

    # Tampilkan ringkasan
    kolom_tampil = ["tid", DT_COL, "sisa_pagu", "ratas_harian",
                    "prediksi_hari", "tanggal_habis"]
    kolom_ada = [k for k in kolom_tampil if k in df.columns]
    print("\n📊 HASIL PREDIKSI (20 ATM TERAWAL):")
    print(df[kolom_ada].head(20).to_string())
    print(f"\n📊 STATISTIK:")
    print(f"  Total ATM         : {len(df)}")
    print(f"  Rata-rata prediksi: {df['prediksi_hari'].mean():.1f} hari")
    print(f"  Min prediksi      : {df['prediksi_hari'].min()} hari")
    print(f"  Max prediksi      : {df['prediksi_hari'].max()} hari")
    print(f"\n📊 DISTRIBUSI STATUS (log only):")
    print(df["threshold"].value_counts().to_string() if "threshold" in df.columns else "(threshold tidak disimpan)")

    return df


# ==========================================================
# 7. UPSERT KE hasil_prediksi (hanya TID terdampak)
# ==========================================================

def ensure_prediction_table_schema(conn) -> None:
    """Pastikan tabel hasil_prediksi punya kolom sesuai skema terbaru."""
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {PREDICTION_TABLE} (
            tid           VARCHAR(50),
            {DT_COL}      DATETIME,
            total_lmb     BIGINT,
            pagu_existing BIGINT,
            sisa_pagu     BIGINT,
            ratas_harian  INT,
            prediksi_hari INT,
            tanggal_habis VARCHAR(20),
            prediksi_at   DATETIME
        )
    """))

    existing_cols = {
        row[0]
        for row in conn.execute(text("""
            SELECT COLUMN_NAME
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = :table_name
        """), {"table_name": PREDICTION_TABLE}).fetchall()
    }

    required_columns = {
        "selisih_lmb": "ALTER TABLE {table_name} ADD COLUMN selisih_lmb INT NULL",
    }

    for col_name, ddl_template in required_columns.items():
        if col_name not in existing_cols:
            conn.execute(text(ddl_template.format(table_name=PREDICTION_TABLE)))


def save_predictions(df: pd.DataFrame) -> None:
    """
    UPSERT hasil prediksi ke tabel hasil_prediksi.
    Hanya TID yang baru diprediksi yang diupdate.
    TID lain tidak disentuh.
    """
    print(f"\n💾 UPSERT ke tabel '{PREDICTION_TABLE}'...")

    kolom_simpan = [
        "tid", DT_COL, "total_lmb", "pagu_existing", "sisa_pagu",
        "ratas_harian", "selisih_lmb", "prediksi_hari", "tanggal_habis",
        "prediksi_at",
    ]
    kolom_ada = [k for k in kolom_simpan if k in df.columns]
    df_save   = df[kolom_ada].copy()

    # Cast tipe data
    df_save["tid"]           = df_save["tid"].astype(str)
    df_save[DT_COL]          = pd.to_datetime(df_save[DT_COL])
    df_save["tanggal_habis"] = df_save["tanggal_habis"].astype(str)
    df_save["prediksi_at"]   = pd.to_datetime(df_save["prediksi_at"])

    for col in ["total_lmb", "pagu_existing", "sisa_pagu",
                "ratas_harian", "selisih_lmb", "prediksi_hari"]:
        if col in df_save.columns:
            df_save[col] = (
                pd.to_numeric(df_save[col], errors="coerce").fillna(0).astype("int64")
            )

    dtype_map = {
        "tid":           String(50),
        DT_COL:          DateTime(),
        "total_lmb":     BigInteger(),
        "pagu_existing": BigInteger(),
        "sisa_pagu":     BigInteger(),
        "ratas_harian":  Integer(),
        "selisih_lmb":   Integer(),
        "prediksi_hari": Integer(),
        "tanggal_habis": String(20),
        "prediksi_at":   DateTime(),
    }
    dtype_map = {k: v for k, v in dtype_map.items() if k in df_save.columns}

    affected_tids = df_save["tid"].tolist()
    staging_table = f"_staging_pred_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    engine = get_db_engine()
    with engine.begin() as conn:
        # 1. Pastikan tabel hasil_prediksi punya skema baru
        ensure_prediction_table_schema(conn)

        # 2. Tulis ke staging
        df_save.to_sql(
            name=staging_table,
            con=conn,
            if_exists="replace",
            index=False,
            chunksize=500,
            dtype=dtype_map,
        )

        # 3. DELETE baris lama untuk TID terdampak
        placeholders = ", ".join([f"'{t}'" for t in affected_tids])
        conn.execute(text(
            f"DELETE FROM {PREDICTION_TABLE} WHERE tid IN ({placeholders})"
        ))

        # 4. INSERT dari staging
        cols = ", ".join(df_save.columns.tolist())
        conn.execute(text(f"""
            INSERT INTO {PREDICTION_TABLE} ({cols})
            SELECT {cols} FROM {staging_table}
        """))

        # 5. Drop staging
        conn.execute(text(f"DROP TABLE IF EXISTS {staging_table}"))

    print(f"✅ UPSERT selesai: {len(df_save)} baris ({len(affected_tids)} TID diperbarui)")


# ==========================================================
# MAIN
# ==========================================================

def main():
    now = datetime.now()
    print("=" * 70)
    print("PREDIKSI REALTIME TANGGAL HABIS ATM")
    print(f"Waktu eksekusi : {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    try:
        engine = get_db_engine()

        # 1. Cek apakah ada data RAW baru
        max_updated, affected_tids, is_new = check_new_raw(engine)

        if not is_new:
            print("\n⏭️  Tidak ada data baru. Prediksi di-skip.")
            return None

        # 2. Preprocessing sudah dijalankan oleh scheduler sebelum memanggil ini.
        #    Load 1 baris terbaru per TID dari preprocessing.
        df_all = load_latest_from_preprocessing(engine)

        if df_all.empty:
            print("❌ preprocessing kosong. Pastikan data_preprocessing.py sudah jalan.")
            return None

        # 3. Filter hanya TID yang punya data baru
        df_terdampak = filter_affected_tids(df_all, affected_tids)

        if df_terdampak.empty:
            print("⏭️  Tidak ada TID terdampak yang ditemukan di preprocessing.")
            return None

        # 4. Validasi fitur
        df_ready = validate_features(df_terdampak)

        # 5. Load model
        model, scaler, fitur = load_model()

        # 6. Prediksi
        df_hasil = predict(df_ready, model, scaler, fitur)

        # 7. Business rule fallback
        df_hasil = apply_business_rule_fallback(df_hasil)
        df_hasil = normalize_prediction_days(df_hasil)

        # 8. UPSERT hanya TID terdampak
        save_predictions(df_hasil)

        print("\n" + "=" * 70)
        print("✅ SELESAI! Prediksi realtime berhasil.")
        print(f"   {len(df_hasil)} ATM diprediksi ulang dari {len(affected_tids)} TID terdampak")
        print("=" * 70)

        return df_hasil

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
