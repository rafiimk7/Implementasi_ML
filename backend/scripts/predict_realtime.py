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

# Tabel sumber data realtime (sesuaikan jika berbeda)
REALTIME_TABLE   = os.getenv("SOURCE_TABLE", "data_maret2026")  # bisa di-override via env var
PREPROCESS_TABLE = "preprocessing"
PREDICTION_TABLE = "hasil_prediksi"
DT_COL           = "updated"

# Konfigurasi fitur kalender cerdas (harus konsisten dengan data_preprocessing.py)
PAYDAY_DATE          = os.getenv("PAYDAY_DATE", "25")
CALENDARIFIC_API_KEY = os.getenv("CALENDARIFIC_API_KEY", "")
HOLIDAY_COUNTRY      = os.getenv("HOLIDAY_COUNTRY", "ID")

print(f"[CONFIG] REALTIME_TABLE      : {REALTIME_TABLE}")
print(f"[CONFIG] PAYDAY_DATE         : {PAYDAY_DATE}")
print(f"[CONFIG] HOLIDAY_COUNTRY     : {HOLIDAY_COUNTRY}")
print(f"[CONFIG] CALENDARIFIC_API_KEY: {'*SET*' if CALENDARIFIC_API_KEY else '(tidak diset — pakai fallback)'}")

# Fitur harus sama persis dengan yang dipakai saat training (17 fitur)
FITUR_ML = [
    # Fitur balance & usage
    "sisa_pagu",
    "ratas_harian",
    "selisih_lmb",
    # Fitur kalender dasar
    "hari",
    "bulan",
    "tahun",
    "hari_ke",
    "kuartal",
    # Cyclic encoding
    "hari_sin",
    "hari_cos",
    "bulan_sin",
    "bulan_cos",
    "hari_ke_sin",
    "hari_ke_cos",
    # Fitur kalender cerdas (is_* = 0/1 flag)
    "is_weekend",
    "is_payday",
    "is_holiday",
]


# ==========================================================
# 1. LOAD DATA REALTIME (RECORD TERBARU PER TID)
# ==========================================================

def load_realtime_data() -> pd.DataFrame:
    """
    Membaca record terbaru per TID dari tabel realtime.
    Menggunakan subquery MAX(updated) untuk efisiensi.
    """
    print("=" * 70)
    print("LOAD DATA REALTIME")
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
    print(f"Data realtime dimuat : {len(df)} TID, {len(df.columns)} kolom")
    print(f"Timestamp terbaru    : {df[DT_COL].max() if not df.empty else 'Tidak ada data'}")
    return df


# ==========================================================
# 2. LOAD HISTORIS PER TID DARI TABEL PREPROCESSING
# ==========================================================

def load_historis_data() -> pd.DataFrame:
    """
    Mengambil ratas_harian dan selisih_lmb terbaru per TID dari tabel preprocessing.
    Mengambil record dengan tanggal terakhir untuk setiap TID.
    """
    query = f"""
        SELECT 
            p.tid,
            p.ratas_harian,
            p.selisih_lmb,
            p.tanggal AS tanggal_historis
        FROM {PREPROCESS_TABLE} p
        INNER JOIN (
            SELECT tid, MAX(tanggal) AS max_tanggal
            FROM {PREPROCESS_TABLE}
            WHERE ratas_harian > 0
            GROUP BY tid
        ) latest
        ON p.tid = latest.tid
        AND p.tanggal = latest.max_tanggal
    """
    try:
        engine = get_db_engine()
        df_hist = pd.read_sql(query, con=engine)
        
        # Jika ada duplikat TID (multiple records di tanggal yang sama), ambil yang pertama
        df_hist = df_hist.drop_duplicates(subset=["tid"], keep="first")
        
        print(f"Data historis dimuat untuk {len(df_hist)} TID")
        if not df_hist.empty:
            print(f"  Rata-rata ratas_harian: {df_hist['ratas_harian'].mean():.1f}")
            print(f"  Rata-rata selisih_lmb : {df_hist['selisih_lmb'].mean():.1f}")
            print(f"  Tanggal historis terakhir: {df_hist['tanggal_historis'].max()}")
        
        return df_hist
    except Exception as e:
        print(f"Tabel preprocessing tidak tersedia atau kosong: {e}")
        print("  ratas_harian dan selisih_lmb akan diestimasi dari data realtime.")
        return pd.DataFrame(columns=["tid", "ratas_harian", "selisih_lmb", "tanggal_historis"])


# ==========================================================
# 3. PREPROCESSING RINGAN DATA REALTIME
# ==========================================================

def preprocess_realtime(df: pd.DataFrame, df_hist: pd.DataFrame) -> pd.DataFrame:
    """
    Preprocessing minimal untuk data realtime:
    - Konversi tipe data
    - Hitung total_lmb & sisa_pagu
    - Gabungkan ratas_harian dan selisih_lmb dari historis
    - Feature engineering dari kolom updated
    """
    print("\n" + "=" * 70)
    print("PREPROCESSING REALTIME")
    print("=" * 70)

    if df.empty:
        raise ValueError("Tidak ada data realtime untuk diprediksi.")

    # ----------------------------------------------------------
    # KONVERSI TIPE DATA
    # ----------------------------------------------------------
    # DB memiliki dua format updated:
    #   "01 Apr 2026 07:45"      → string lokal
    #   "2026-04-01 00:15:15"    → ISO datetime
    # format="mixed" di pandas 2.x menangani keduanya sekaligus
    df[DT_COL] = pd.to_datetime(df[DT_COL], format="mixed", dayfirst=True, errors="coerce")
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
    # HITUNG TOTAL LMB & SISA PAGU
    # ----------------------------------------------------------
    df["total_lmb"] = df[kolom_lmb].sum(axis=1)
    df["sisa_pagu"] = (
        df["pagu_existing"] - df["total_lmb"]
    ).clip(lower=0).astype(int)

    # ----------------------------------------------------------
    # GABUNGKAN RATAS_HARIAN & SELISIH_LMB DARI HISTORIS
    # ----------------------------------------------------------
    if not df_hist.empty:
        # Merge dengan data historis - LEFT JOIN
        df = df.merge(
            df_hist[["tid", "ratas_harian", "selisih_lmb"]],
            on="tid",
            how="left"
        )
        
        print(f"  Berhasil merge data historis untuk {df['ratas_harian'].notna().sum()} TID")
    else:
        # Jika tidak ada data historis, buat kolom kosong
        df["ratas_harian"] = np.nan
        df["selisih_lmb"] = np.nan

    # ----------------------------------------------------------
    # FALLBACK UNTUK TID BARU / TANPA HISTORIS
    # ----------------------------------------------------------
    # Untuk TID baru yang tidak ada di historis:
    # 1. ratas_harian = rata-rata dari TID yang ada, atau estimasi dari sisa_pagu / 7 hari
    # 2. selisih_lmb = rata-rata dari TID yang ada, atau estimasi dari total_lmb * 0.3
    
    tid_tanpa_historis = df["ratas_harian"].isna().sum()
    if tid_tanpa_historis > 0:
        print(f"  ⚠️ {tid_tanpa_historis} TID tidak ada di historis, menggunakan estimasi fallback")
        
        # Hitung rata-rata dari TID yang ada historis
        mean_ratas = df[df["ratas_harian"].notna()]["ratas_harian"].mean()
        mean_selisih = df[df["selisih_lmb"].notna()]["selisih_lmb"].mean()
        
        if pd.isna(mean_ratas) or mean_ratas <= 0:
            # Jika semua TID baru, gunakan asumsi default konservatif
            mean_ratas = max(1, df["sisa_pagu"].mean() / 7) if df["sisa_pagu"].mean() > 0 else 50000
        
        if pd.isna(mean_selisih) or mean_selisih <= 0:
            # Estimasi selisih dari total_lmb (asumsi 30% dari total dipakai per hari)
            mean_selisih = max(1, df["total_lmb"].mean() * 0.3) if df["total_lmb"].mean() > 0 else 30000
        
        # Fill NA dengan estimasi
        df.loc[df["ratas_harian"].isna(), "ratas_harian"] = np.ceil(mean_ratas)
        df.loc[df["selisih_lmb"].isna(), "selisih_lmb"] = np.ceil(mean_selisih)

    # Pastikan tidak ada nilai 0, negatif, NaN, atau inf
    df["ratas_harian"] = df["ratas_harian"].replace([0, np.inf, -np.inf], np.nan).fillna(1)
    df["selisih_lmb"] = df["selisih_lmb"].replace([0, np.inf, -np.inf], np.nan).fillna(1)
    
    df["ratas_harian"] = np.ceil(np.maximum(df["ratas_harian"], 1)).astype(int)
    df["selisih_lmb"] = np.ceil(np.maximum(df["selisih_lmb"], 1)).astype(int)

    # ----------------------------------------------------------
    # VALIDASI SISA PAGU
    # ----------------------------------------------------------
    # Jika sisa_pagu = 0, prediksi akan selalu 0 hari
    # Beri peringatan
    zero_sisa = (df["sisa_pagu"] == 0).sum()
    if zero_sisa > 0:
        print(f"  ⚠️ {zero_sisa} TID memiliki sisa_pagu = 0 (saldo habis)")

    # ----------------------------------------------------------
    # FEATURE ENGINEERING DARI KOLOM UPDATED
    # ----------------------------------------------------------
    df["hari"]    = df[DT_COL].dt.day
    df["bulan"]   = df[DT_COL].dt.month
    df["tahun"]   = df[DT_COL].dt.year
    df["hari_ke"] = df[DT_COL].dt.dayofyear

    # -- Kuartal --
    df["kuartal"] = df[DT_COL].dt.quarter

    # -- Cyclic encoding --
    df["hari_sin"]    = np.sin(2 * np.pi * df["hari"]    / 31)
    df["hari_cos"]    = np.cos(2 * np.pi * df["hari"]    / 31)
    df["bulan_sin"]   = np.sin(2 * np.pi * df["bulan"]   / 12)
    df["bulan_cos"]   = np.cos(2 * np.pi * df["bulan"]   / 12)
    df["hari_ke_sin"] = np.sin(2 * np.pi * df["hari_ke"] / 365)
    df["hari_ke_cos"] = np.cos(2 * np.pi * df["hari_ke"] / 365)

    # ----------------------------------------------------------
    # FITUR KALENDER CERDAS (is_weekend, is_payday, is_holiday)
    # Harus konsisten dengan yang dihasilkan data_preprocessing.py
    # ----------------------------------------------------------
    engine = get_db_engine()
    df = add_calendar_flags(
        df,
        dt_col=DT_COL,
        engine=engine,
        payday_config=PAYDAY_DATE,
        api_key=CALENDARIFIC_API_KEY,
        country=HOLIDAY_COUNTRY,
    )

    print(f"\nPreprocessing selesai : {len(df)} record siap diprediksi")
    print(f"  Rata-rata ratas_harian: {df['ratas_harian'].mean():.1f}")
    print(f"  Rata-rata selisih_lmb : {df['selisih_lmb'].mean():.1f}")
    print(f"  Rata-rata sisa_pagu   : {df['sisa_pagu'].mean():.0f}")
    print(f"  Jumlah fitur siap     : {len(FITUR_ML)}")
    print(f"  is_weekend            : {df['is_weekend'].sum()} ATM")
    print(f"  is_payday             : {df['is_payday'].sum()} ATM")
    print(f"  is_holiday            : {df['is_holiday'].sum()} ATM")
    
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
    df["threshold"] = pd.cut(
        df["prediksi_hari"],
        bins=[-1, 1, 2, 3, float('inf')],
        labels=['🔴 Kritis', '🟠 Tinggi', '🟡 Sedang', '🟢 Aman']
    )

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

        # 2. Load data historis dari tabel preprocessing
        df_hist = load_historis_data()

        # 3. Preprocessing ringan + feature engineering
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