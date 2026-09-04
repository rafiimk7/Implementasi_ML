#!/usr/bin/env python
"""
Prediksi Realtime ATM
---------------------
Membaca data terbaru per TID dari database MySQL,
menerapkan preprocessing ringan + feature engineering,
lalu memuat model yang sudah dilatih untuk memprediksi
estimasi jumlah hari dan tanggal habis saldo ATM.

Hasil disimpan ke tabel `hasil_prediksi` di database yang sama.

Alur:
  1. Baca data terbaru per TID dari tabel realtime
  2. Ambil ratas_harian dan selisih_lmb historis dari tabel `preprocessing`
  3. Hitung total_lmb, sisa_pagu, feature engineering
  4. Load model dari models/*.pkl
  5. Prediksi jumlah_hari & tanggal_habis
  6. Simpan ke tabel `hasil_prediksi`
"""

import sys
import warnings
import os
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ----------------------------------------------------------
# PATH & KONFIGURASI
# ----------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR   = PROJECT_ROOT / "models"

sys.path.insert(0, str(PROJECT_ROOT))
from config.config import get_db_engine
from calendar_features import add_calendar_flags

# Tabel sumber data realtime untuk inferensi HARUS memakai hasil preprocessing,
# bukan tabel raw dari .env atau dataset mentah.
# Ini penting agar fitur model yang dilatih cocok dengan data yang diprediksi.
REALTIME_TABLE   = os.getenv("REALTIME_TABLE") or "preprocessing"
PREPROCESS_TABLE = os.getenv("PREPROCESS_TABLE") or "preprocessing"
PREDICTION_TABLE = os.getenv("PREDICTION_TABLE") or "hasil_prediksi"
DT_COL           = "updated"

# Konfigurasi fitur kalender cerdas (harus konsisten dengan data_preprocessing.py)
PAYDAY_DATE          = os.getenv("PAYDAY_DATE", "25")
CALENDARIFIC_API_KEY = os.getenv("CALENDARIFIC_API_KEY", "")
HOLIDAY_COUNTRY      = os.getenv("HOLIDAY_COUNTRY", "ID")

print(f"[CONFIG] REALTIME_TABLE      : {REALTIME_TABLE}")
print(f"[CONFIG] PAYDAY_DATE         : {PAYDAY_DATE}")
print(f"[CONFIG] HOLIDAY_COUNTRY     : {HOLIDAY_COUNTRY}")
print(f"[CONFIG] CALENDARIFIC_API_KEY: {'*SET*' if CALENDARIFIC_API_KEY else '(tidak diset — pakai fallback)'}")

# Fitur harus sama persis dengan yang dipakai saat training.
# Kita tidak hardcode lagi, melainkan memuat daftar fitur dari file model yang
# sudah disimpan oleh `train_model.py` agar inferensi tetap konsisten.
def get_model_feature_list():
    feature_file = MODELS_DIR / "fitur.pkl"
    if feature_file.exists():
        return joblib.load(feature_file)

    # fallback: gunakan definisi yang sama dari train_model.py jika model belum ada
    try:
        from train_model import FITUR_ML
        return FITUR_ML
    except Exception:
        raise FileNotFoundError(
            "File model belum dibuat. Jalankan train_model.py terlebih dahulu."
        )


FITUR_ML = get_model_feature_list()


# ==========================================================
# 1. LOAD DATA REALTIME (RECORD TERBARU PER TID)
# ==========================================================

def load_realtime_data() -> pd.DataFrame:
    """
    Membaca record terbaru per TID dari tabel preprocessing.
    Karena model dilatih pada fitur yang sudah terbentuk di preprocessing,
    inferensi harus memakai data hasil preprocessing yang sama.
    """
    print("=" * 70)
    print("LOAD DATA PREPROCESSING TERBARU")
    print("=" * 70)

    query = f"""
        SELECT t.*
        FROM {REALTIME_TABLE} t
        INNER JOIN (
            SELECT tid, MAX(updated) AS max_updated
            FROM {REALTIME_TABLE}
            GROUP BY tid
        ) latest
        ON t.tid = latest.tid
        AND t.updated = latest.max_updated
    """

    engine = get_db_engine()
    df = pd.read_sql(query, con=engine)
    print(f"Data preprocessing dimuat : {len(df)} TID, {len(df.columns)} kolom")
    print(f"Timestamp terbaru          : {df[DT_COL].max() if not df.empty else 'Tidak ada data'}")
    return df


# ==========================================================
# 2. LOAD HISTORIS PER TID DARI TABEL PREPROCESSING
# ==========================================================

def load_historis_data() -> pd.DataFrame:
    """
    Mengambil record terbaru dari tabel preprocessing agar data inferensi
    mengikuti satu snapshot per TID yang sama dengan model dilatih.
    """
    query = f"""
        SELECT t.*
        FROM {PREPROCESS_TABLE} t
        INNER JOIN (
            SELECT tid, MAX(updated) AS max_updated
            FROM {PREPROCESS_TABLE}
            GROUP BY tid
        ) latest
        ON t.tid = latest.tid
        AND t.updated = latest.max_updated
    """
    try:
        engine = get_db_engine()
        df_hist = pd.read_sql(query, con=engine)
        print(f"Data historis dimuat untuk {len(df_hist)} TID")
        if not df_hist.empty:
            print(f"  Rata-rata ratas_harian: {df_hist['ratas_harian'].mean():.1f}")
            print(f"  Rata-rata selisih_lmb : {df_hist['selisih_lmb'].mean():.1f}")
            print(f"  Tanggal historis terakhir: {df_hist['updated'].max()}")
        return df_hist
    except Exception as e:
        print(f"Tabel preprocessing tidak tersedia atau kosong: {e}")
        return pd.DataFrame()


# ==========================================================
# 3. PREPROCESSING RINGAN DATA REALTIME
# ==========================================================

def preprocess_realtime(df: pd.DataFrame, df_hist: pd.DataFrame) -> pd.DataFrame:
    """
    Validasi dan persiapan data hasil preprocessing untuk inferensi.
    Data yang masuk ke fungsi ini sudah merupakan output dari `data_preprocessing.py`
    dan sudah memiliki semua fitur yang dibutuhkan model.
    """
    print("\n" + "=" * 70)
    print("VALIDASI DATA PREPROCESSING")
    print("=" * 70)

    if df.empty:
        raise ValueError("Tidak ada data preprocessing untuk diprediksi.")

    df = df.copy()
    df[DT_COL] = pd.to_datetime(df[DT_COL], errors="coerce")
    df["tanggal"] = df[DT_COL].dt.date

    missing_cols = [col for col in FITUR_ML if col not in df.columns]
    if missing_cols:
        raise ValueError(
            "Data preprocessing tidak memiliki kolom fitur model: "
            f"{missing_cols}. Jalankan data_preprocessing.py / train_model.py terlebih dahulu."
        )

    for col in FITUR_ML:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # jika ada missing value di fitur model, isi dengan median per kolom
    for col in FITUR_ML:
        if df[col].isna().any():
            median_val = df[col].median()
            df[col] = df[col].fillna(median_val)

    print(f"\nPreprocessing selesai : {len(df)} record siap diprediksi")
    print(f"  Jumlah fitur siap     : {len(FITUR_ML)}")
    print(f"  Kolom utama           : {['tid', DT_COL, 'sisa_pagu', 'ratas_harian']}")
    return df


# ==========================================================
# 4. LOAD MODEL DARI DISK
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

    print(f"\n✅ Model dimuat dari  : {model_path}")
    print(f"   Jumlah fitur      : {len(fitur)}")
    print(f"   Fitur model       : {fitur[:5]}...")
    return model, scaler, fitur


# ==========================================================
# 5. PREDIKSI
# ==========================================================

def assign_threshold(df: pd.DataFrame) -> pd.DataFrame:
    """Menetapkan status threshold berdasarkan prediksi_hari."""
    df = df.copy()
    df["threshold"] = pd.cut(
        df["prediksi_hari"],
        bins=[-1, 1, 2, 3, float("inf")],
        labels=["🔴 Kritis", "🟠 Tinggi", "🟡 Sedang", "🟢 Aman"],
        right=True,
    )
    return df


def predict(df: pd.DataFrame, model, scaler, fitur: list) -> pd.DataFrame:
    """Menjalankan prediksi jumlah_hari dan menghitung tanggal_habis."""
    print("\n" + "=" * 70)
    print("PREDIKSI")
    print("=" * 70)

    # Validasi fitur
    fitur_kurang = [f for f in fitur if f not in df.columns]
    if fitur_kurang:
        raise ValueError(f"Kolom fitur tidak tersedia: {fitur_kurang}")

    # Siapkan data untuk prediksi
    X = df[fitur].copy()

    # Handle missing values di X
    for col in fitur:
        if X[col].isna().any():
            median_val = X[col].median() if len(X) > 0 else 0
            X[col] = X[col].fillna(median_val) 

    X_scaled = scaler.transform(X)

    # Prediksi
    prediksi_hari = np.ceil(model.predict(X_scaled)).astype(int)
    prediksi_hari = np.maximum(prediksi_hari, 0)  # Tidak boleh negatif

    df = df.copy()
    df["prediksi_hari"] = prediksi_hari
    df["tanggal_habis"] = (
        pd.to_datetime(df[DT_COL]) +
        pd.to_timedelta(df["prediksi_hari"], unit="D")
    ).dt.strftime("%d-%m-%Y")

    df["prediksi_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Tambahkan threshold untuk monitoring
    df = assign_threshold(df)

    # Tampilkan hasil
    kolom_tampil = [
        "tid", DT_COL, "sisa_pagu",
        "ratas_harian", "selisih_lmb", "prediksi_hari", 
        "tanggal_habis", "threshold"
    ]
    kolom_ada = [k for k in kolom_tampil if k in df.columns]
    
    print("\n📊 HASIL PREDIKSI (20 ATM TERAWAL):")
    print(df[kolom_ada].head(20).to_string())

    print(f"\n📊 STATISTIK PREDIKSI:")
    print(f"  Total ATM         : {len(df)}")
    print(f"  Rata-rata prediksi: {df['prediksi_hari'].mean():.1f} hari")
    print(f"  Min prediksi      : {df['prediksi_hari'].min()} hari")
    print(f"  Max prediksi      : {df['prediksi_hari'].max()} hari")
    print(f"  Median prediksi   : {df['prediksi_hari'].median():.1f} hari")
    
    # Distribusi threshold
    print(f"\n📊 DISTRIBUSI THRESHOLD:")
    print(df['threshold'].value_counts().to_string())

    return df


# ==========================================================
# 6. SIMPAN HASIL KE DATABASE
# ==========================================================

def save_predictions(df: pd.DataFrame) -> None:
    """Menyimpan hasil prediksi ke tabel hasil_prediksi - hanya kolom esensial."""
    from sqlalchemy import BigInteger, DateTime, Integer, String
    
    print(f"\n💾 Menyimpan hasil ke tabel '{PREDICTION_TABLE}'...")

    # Kolom ESENSIAL untuk dashboard
    kolom_simpan = [
        "tid",
        DT_COL,
        "total_lmb",
        "pagu_existing",
        "sisa_pagu",
        "ratas_harian",
        "selisih_lmb",
        "prediksi_hari",
        "tanggal_habis",
        "threshold",
        "prediksi_at", 
    ]
    kolom_ada = [k for k in kolom_simpan if k in df.columns]
    
    df_save = df[kolom_ada].copy()
    
    # Casting tipe data
    df_save["tid"]           = df_save["tid"].astype(str)
    df_save[DT_COL]          = pd.to_datetime(df_save[DT_COL])
    df_save["tanggal_habis"] = df_save["tanggal_habis"].astype(str)
    df_save["threshold"]     = df_save["threshold"].astype(str) if "threshold" in df_save.columns else None
    df_save["prediksi_at"]   = pd.to_datetime(df_save["prediksi_at"])

    for col in ["total_lmb", "pagu_existing", "sisa_pagu", "ratas_harian", "selisih_lmb", "prediksi_hari"]:
        if col in df_save.columns:
            df_save[col] = pd.to_numeric(df_save[col], errors="coerce").fillna(0).astype("int64")

    # Dtype map untuk MySQL
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
        "threshold":     String(20),
        "prediksi_at":   DateTime(),
    }
    dtype_map = {k: v for k, v in dtype_map.items() if k in df_save.columns}
    
    print(f"  Kolom yang disimpan: {list(df_save.columns)}")

    engine = get_db_engine()
    df_save.to_sql(
        name=PREDICTION_TABLE,
        con=engine,
        if_exists="replace",
        index=False,
        chunksize=1000,
        dtype=dtype_map,
    )
    print(f"✅ Berhasil menyimpan {len(df_save)} baris ke tabel '{PREDICTION_TABLE}'")


# ==========================================================
# 7. LOGIKA BUSINESS RULE FALLBACK (OPSIONAL)
# ==========================================================

def apply_business_rule_fallback(df: pd.DataFrame) -> pd.DataFrame:
    """
    Opsional: Menghasilkan prediksi menggunakan business rule sebagai fallback
    jika model tidak tersedia atau prediksi tidak masuk akal.
    """
    print("\n" + "=" * 70)
    print("BUSINESS RULE FALLBACK")
    print("=" * 70)

    # Business rule: ceil(sisa_pagu / ratas_harian)
    df = df.copy()
    df["business_rule_hari"] = (
        np.ceil(
            df["sisa_pagu"] /
            df["ratas_harian"].replace(0, np.nan)
        )
        .fillna(0)
        .astype(int)
    )

    # Jika prediksi model terlalu jauh dari business rule, gunakan business rule
    if "prediksi_hari" in df.columns:
        diff = np.abs(df["prediksi_hari"] - df["business_rule_hari"])
        # Hindari division by zero
        denominator = df["business_rule_hari"].replace(0, 1)
        diff_pct = (diff / denominator) * 100

        # Jika prediksi model menyimpang > 50%, gunakan business rule
        gunakan_business_rule = diff_pct > 50
        if gunakan_business_rule.any():
            print(f"  ⚠️ {gunakan_business_rule.sum()} TID menggunakan business rule fallback")
            df.loc[gunakan_business_rule, "prediksi_hari"] = df.loc[gunakan_business_rule, "business_rule_hari"]
            df.loc[gunakan_business_rule, "tanggal_habis"] = (
                pd.to_datetime(df.loc[gunakan_business_rule, DT_COL]) +
                pd.to_timedelta(df.loc[gunakan_business_rule, "business_rule_hari"], unit="D")
            ).dt.strftime("%d-%m-%Y")

    # Recompute threshold setelah prediksi bisa berubah oleh fallback.
    df = assign_threshold(df)
    return df


# ==========================================================
# MAIN
# ==========================================================

def main():
    print("=" * 70)
    print("PREDIKSI REALTIME TANGGAL HABIS ATM")
    print(f"Waktu eksekusi : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    try:
        # 1. Load data terbaru per TID dari tabel realtime
        df_realtime = load_realtime_data()
        
        if df_realtime.empty:
            print("❌ Tidak ada data realtime untuk diprediksi.")
            return None

        # 2. Load data terbaru dari tabel preprocessing (output hasil feature engineering)
        df_hist = load_historis_data()

        # 3. Validasi dan cek fitur sesuai model dilatih.
        df_ready = preprocess_realtime(df_realtime, df_hist)

        # 4. Load model dari disk
        model, scaler, fitur = load_model()

        # 5. Prediksi
        df_hasil = predict(df_ready, model, scaler, fitur)

        # 6. (Opsional) Apply business rule fallback
        df_hasil = apply_business_rule_fallback(df_hasil)

        # 7. Simpan ke tabel hasil_prediksi
        save_predictions(df_hasil)

        print("\n" + "=" * 70)
        print("✅ SELESAI! Prediksi realtime berhasil.")
        print(f"   {len(df_hasil)} ATM diprediksi")
        print("=" * 70)

        return df_hasil

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()