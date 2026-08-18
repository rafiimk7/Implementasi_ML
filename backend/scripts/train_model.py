#!/usr/bin/env python
"""
Training Model ML untuk Prediksi Tanggal Habis ATM
----------------------------------------------------
Membaca data dari tabel `preprocessing` di MySQL
(sudah termasuk feature engineering),
melatih model RandomForest, menyimpan model ke disk,
dan hasil prediksi ke tabel `hasil_prediksi` di database.
"""

import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

# ----------------------------------------------------------
# PATH & KONFIGURASI
# ----------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR   = PROJECT_ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PROJECT_ROOT))
from config.config import get_db_engine

PREPROCESS_TABLE = "preprocessing"
PREDICTION_TABLE = "hasil_prediksi"
DT_COL           = "updated"

# Fitur yang dihasilkan oleh data_preprocessing.py (17 fitur total)
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
    # Fitur kalender cerdas (flag + jarak ke event)
    "is_weekend",
    "is_payday",
    "is_holiday",
    "days_to_payday",
    "days_since_payday",
    "is_near_holiday_3d",
    # Trend historis + interaction tren-event
    "rolling_7d",
    "rolling_14d",
    "trend_7d_ratio",
    "trend_14d_ratio",
    "weekend_x_ratas_harian",
    "payday_x_sisa_pagu",
    "holiday_x_ratas_harian",
    "weekend_x_trend",
    "payday_x_trend",
    "holiday_x_trend",
]
TARGET = "jumlah_hari"


# ==========================================================
# 1. LOAD DATA DARI TABEL PREPROCESSING
# ==========================================================

def load_preprocessing() -> pd.DataFrame:
    print("=" * 70)
    print("LOAD DATA DARI TABEL PREPROCESSING")
    print("=" * 70)

    engine = get_db_engine()
    df = pd.read_sql(f"SELECT * FROM {PREPROCESS_TABLE}", con=engine)
    print(f"Data berhasil dimuat : {len(df)} baris, {len(df.columns)} kolom")
    
    # Validasi kolom wajib
    kolom_wajib = FITUR_ML + [TARGET, "tid", DT_COL]
    kolom_kurang = [k for k in kolom_wajib if k not in df.columns]
    if kolom_kurang:
        raise ValueError(f"Kolom wajib tidak ditemukan: {kolom_kurang}")
    
    # CAST tipe data
    df[DT_COL] = pd.to_datetime(df[DT_COL])
    df["tanggal"] = df[DT_COL].dt.date
    
    return df


# ==========================================================
# 2. VALIDASI TARGET DENGAN BUSINESS RULE
# ==========================================================

def validate_target(df: pd.DataFrame) -> pd.DataFrame:
    """
    Memastikan target 'jumlah_hari' sesuai dengan business rule:
    ceil(sisa_pagu / ratas_harian)
    """
    print("\n" + "=" * 70)
    print("VALIDASI TARGET DENGAN BUSINESS RULE")
    print("=" * 70)
    
    # Hitung ulang target berdasarkan business rule
    df["jumlah_hari_check"] = (
        np.ceil(
            df["sisa_pagu"] / 
            df["ratas_harian"].replace(0, np.nan)
        )
        .fillna(0)
        .astype(int)
    )
    
    # Cek konsistensi
    konsisten = (df["jumlah_hari"] == df["jumlah_hari_check"])
    konsisten_pct = konsisten.mean() * 100
    
    print(f"Konsistensi target dengan business rule: {konsisten_pct:.2f}%")
    
    if konsisten_pct < 95:
        print("⚠️ WARNING: Sebagian besar target tidak konsisten!")
        print("   Kemungkinan ada perubahan data setelah preprocessing.")
        print("   Menggunakan hasil perhitungan ulang untuk training.")
        df[TARGET] = df["jumlah_hari_check"]
    
    # Drop kolom temporary
    df = df.drop(columns=["jumlah_hari_check"])
    
    return df


# ==========================================================
# 3. TRAINING MODEL
# ==========================================================

def train(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("TRAINING MODEL")
    print("=" * 70)

    # Pastikan semua fitur tersedia
    fitur_kurang = [f for f in FITUR_ML if f not in df.columns]
    if fitur_kurang:
        raise ValueError(
            f"Kolom fitur berikut tidak ditemukan: {fitur_kurang}\n"
            "Jalankan data_preprocessing.py terlebih dahulu."
        )

    # ==========================================================
    # HANDLE MISSING VALUES & OUTLIERS
    # ==========================================================
    
    # 1. Filter target valid
    df_ml = df[df[TARGET] > 0].copy()

    # 2. Add interaction features before training if not already present
    if "weekend_x_ratas_harian" not in df_ml.columns:
        df_ml["weekend_x_ratas_harian"] = df_ml["is_weekend"] * df_ml["ratas_harian"]
    if "payday_x_sisa_pagu" not in df_ml.columns:
        df_ml["payday_x_sisa_pagu"] = df_ml["is_payday"] * df_ml["sisa_pagu"]
    if "holiday_x_ratas_harian" not in df_ml.columns:
        df_ml["holiday_x_ratas_harian"] = df_ml["is_holiday"] * df_ml["ratas_harian"]
    if "weekend_x_trend" not in df_ml.columns:
        df_ml["weekend_x_trend"] = df_ml["is_weekend"] * df_ml["trend_7d_ratio"]
    if "payday_x_trend" not in df_ml.columns:
        df_ml["payday_x_trend"] = df_ml["is_payday"] * df_ml["trend_7d_ratio"]
    if "holiday_x_trend" not in df_ml.columns:
        df_ml["holiday_x_trend"] = df_ml["is_holiday"] * df_ml["trend_7d_ratio"]

    # 3. Handle missing values - imputasi dengan median
    for col in FITUR_ML:
        median_val = df_ml[col].median()
        df_ml[col] = df_ml[col].fillna(median_val)
    
    # 3. Handle outliers - winsorization (clip ke percentile 1% dan 99%)
    for col in ["selisih_lmb", "ratas_harian"]:
        lower = df_ml[col].quantile(0.01)
        upper = df_ml[col].quantile(0.99)
        df_ml[col] = df_ml[col].clip(lower, upper)
    
    print(f"Jumlah data training setelah cleaning : {len(df_ml)} record")
    print(f"Jumlah fitur                          : {len(FITUR_ML)}")

    if len(df_ml) < 10:
        raise ValueError(
            f"Data terlalu sedikit ({len(df_ml)} record). "
            "Pastikan tabel preprocessing sudah terisi."
        )

    X = df_ml[FITUR_ML]
    y = df_ml[TARGET]

    # ==========================================================
    # SPLIT DATA
    # ==========================================================
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    # ==========================================================
    # SCALING
    # ==========================================================
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    # ==========================================================
    # TRAINING
    # ==========================================================
    model = RandomForestRegressor(
        n_estimators=100,
        max_depth=8,
        min_samples_split=10,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train_scaled, y_train)

    # ==========================================================
    # EVALUASI
    # ==========================================================
    y_pred = model.predict(X_test_scaled)
    mae = mean_absolute_error(y_test, y_pred)
    r2  = r2_score(y_test, y_pred)
    
    # MAPE (Mean Absolute Percentage Error)
    mape = np.mean(np.abs((y_test - y_pred) / y_test)) * 100

    print(f"\nHASIL EVALUASI:")
    print(f"  MAE  : {mae:.2f} hari")
    print(f"  R²   : {r2:.4f}")
    print(f"  MAPE : {mape:.2f}%")
    
    # Feature importance
    feature_importance = pd.DataFrame({
        'feature': FITUR_ML,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    print("\nTOP 5 FEATURE IMPORTANCE:")
    print(feature_importance.head(5).to_string(index=False))

    return model, scaler


# ==========================================================
# 4. PREDIKSI DATA TERBARU PER TID
# ==========================================================

def predict_latest(df: pd.DataFrame, model, scaler) -> pd.DataFrame:
    print("\n" + "=" * 70)
    print("PREDIKSI TANGGAL HABIS (DATA TERBARU PER TID)")
    print("=" * 70)

    # Ambil record terbaru per TID berdasarkan kolom updated
    df_terbaru = (
        df.sort_values(["tid", DT_COL])
          .groupby("tid", as_index=False)
          .last()
    )

    X_pred = df_terbaru[FITUR_ML].copy()
    
    # Handle missing values di prediksi
    for col in FITUR_ML:
        X_pred[col] = X_pred[col].fillna(X_pred[col].median() if len(X_pred) > 0 else 0)
    
    X_pred_scaled = scaler.transform(X_pred)

    prediksi_hari = np.ceil(model.predict(X_pred_scaled)).astype(int)
    prediksi_hari = np.maximum(prediksi_hari, 0)

    df_terbaru["prediksi_hari"] = prediksi_hari
    df_terbaru["tanggal_habis"] = (
        pd.to_datetime(df_terbaru[DT_COL]) +
        pd.to_timedelta(df_terbaru["prediksi_hari"], unit="D")
    ).dt.strftime("%d-%m-%Y")
    
    # Tambahkan threshold berdasarkan business rule
    df_terbaru["threshold"] = pd.cut(
        df_terbaru["prediksi_hari"],
        bins=[-1, 1, 2, 3, float('inf')],
        labels=['🔴 Kritis', '🟠 Tinggi', '🟡 Sedang', '🟢 Aman']
    )

    kolom_tampil = [
        "tid", DT_COL, "sisa_pagu",
        "ratas_harian", "prediksi_hari", "tanggal_habis", "threshold"
    ]
    print("\n📊 HASIL PREDIKSI (20 ATM TERAWAL):")
    print(df_terbaru[kolom_tampil].head(20).to_string())

    print(f"\n📊 STATISTIK PREDIKSI:")
    print(f"  Total ATM         : {len(df_terbaru)}")
    print(f"  Rata-rata prediksi: {df_terbaru['prediksi_hari'].mean():.1f} hari")
    print(f"  Min prediksi      : {df_terbaru['prediksi_hari'].min()} hari")
    print(f"  Max prediksi      : {df_terbaru['prediksi_hari'].max()} hari")
    
    # Distribusi threshold
    print(f"\n📊 DISTRIBUSI THRESHOLD:")
    print(df_terbaru['threshold'].value_counts().to_string())

    return df_terbaru


# ==========================================================
# 5. SIMPAN HASIL PREDIKSI KE DATABASE
# ==========================================================

def save_predictions_to_db(df: pd.DataFrame) -> None:
    """Menyimpan hasil prediksi ke tabel hasil_prediksi - hanya kolom esensial."""
    from sqlalchemy import BigInteger, DateTime, Integer, String
    from datetime import datetime
    
    print(f"\nMenyimpan hasil prediksi ke tabel '{PREDICTION_TABLE}'...")

    # Kolom ESENSIAL untuk dashboard
    kolom_simpan = [
        "tid",
        DT_COL,
        "total_lmb",
        "pagu_existing",
        "sisa_pagu",
        "ratas_harian",
        "prediksi_hari",
        "tanggal_habis",
        "threshold"
    ]
    kolom_ada = [k for k in kolom_simpan if k in df.columns]
    
    df_save = df[kolom_ada].copy()
    
    # Tambahkan timestamp prediksi
    df_save["prediksi_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Casting tipe data
    df_save["tid"]           = df_save["tid"].astype(str)
    df_save[DT_COL]          = pd.to_datetime(df_save[DT_COL])
    df_save["tanggal_habis"] = df_save["tanggal_habis"].astype(str)
    df_save["threshold"]     = df_save["threshold"].astype(str) if "threshold" in df_save.columns else None
    df_save["prediksi_at"]   = pd.to_datetime(df_save["prediksi_at"])

    for col in ["total_lmb", "pagu_existing", "sisa_pagu", "ratas_harian", "prediksi_hari"]:
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
        "prediksi_hari": Integer(),
        "tanggal_habis": String(20),
        "threshold":     String(20),
        "prediksi_at":   DateTime(),
    }
    dtype_map = {k: v for k, v in dtype_map.items() if k in df_save.columns}
    
    print(f"Kolom yang disimpan: {list(df_save.columns)}")

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
# 6. SIMPAN MODEL KE DISK
# ==========================================================

def save_models(model, scaler) -> None:
    joblib.dump(model,    MODELS_DIR / "model_prediksi_habis.pkl")
    joblib.dump(scaler,   MODELS_DIR / "scaler.pkl")
    joblib.dump(FITUR_ML, MODELS_DIR / "fitur.pkl")

    print("\n✅ Model disimpan ke:")
    print(f"  {MODELS_DIR / 'model_prediksi_habis.pkl'}")
    print(f"  {MODELS_DIR / 'scaler.pkl'}")
    print(f"  {MODELS_DIR / 'fitur.pkl'}")


# ==========================================================
# MAIN
# ==========================================================

def main():
    print("=" * 70)
    print("ML PREDIKSI TANGGAL HABIS ATM")
    print("=" * 70)

    try:
        # 1. Load dari tabel preprocessing
        df = load_preprocessing()
        
        # 2. Validasi target dengan business rule
        df = validate_target(df)

        # 3. Training
        model, scaler = train(df)

        # 4. Prediksi data terbaru per TID
        df_hasil = predict_latest(df, model, scaler)

        # 5. Simpan hasil ke tabel hasil_prediksi di database
        save_predictions_to_db(df_hasil)

        # 6. Simpan model ke disk
        save_models(model, scaler)

        print("\n" + "=" * 70)
        print("✅ SELESAI! Model siap digunakan untuk prediksi realtime.")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise


if __name__ == "__main__":
    main()