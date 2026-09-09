#!/usr/bin/env python
"""
Training Model ML — Prediksi Tanggal Habis ATM
------------------------------------------------
Membaca data dari tabel `preprocessing` di MySQL,
melatih model LightGBM (fallback: RandomForest),
menyimpan artefak model ke disk, dan hasil prediksi ke `hasil_prediksi`.
"""

import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

# ----------------------------------------------------------
# PATH & KONFIGURASI
# ----------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR   = PROJECT_ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
VISUALIZATION_DIR = PROJECT_ROOT / "visualizations"
VISUALIZATION_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR = VISUALIZATION_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PROJECT_ROOT))
from config.config import get_db_engine
from scripts.predict_realtime import status_from_hari

PREPROCESS_TABLE = "preprocessing"
PREDICTION_TABLE = "hasil_prediksi"
DT_COL           = "updated"

# Fitur yang dihasilkan oleh data_preprocessing.py (48 fitur)
FITUR_ML = [
    # Balance & usage
    "sisa_pagu",
    "ratas_harian",
    "selisih_lmb",
    # Kalender dasar
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
    # Kalender cerdas (flag + jarak ke event)
    "is_weekend",
    "is_payday",
    "is_holiday",
    "days_to_payday",
    "days_since_payday",
    "is_near_holiday_3d",
    # Trend historis
    "rolling_7d",
    "rolling_14d",
    "rolling_30d",
    "rolling_std_7d",
    "rolling_std_14d",
    "rolling_7d_ratio",
    "trend_7d_ratio",
    "trend_14d_ratio",
    # Interaction: kalender × transaksi
    "weekend_x_ratas_harian",
    "payday_x_sisa_pagu",
    "holiday_x_ratas_harian",
    "weekend_x_trend",
    "payday_x_trend",
    "holiday_x_trend",
    # Lag & weekday Fourier
    "lag_1_ratas",
    "lag_7_ratas",
    "lag_14_ratas",
    "lag_7_sisa_pagu",
    "weekday_sin",
    "weekday_cos",
    "payday_x_weekday_sin",
    "weekend_x_rolling_std_7d",
    # Event / window
    "cum_prev_3d",
    "cum_prev_7d",
    "cum_prev_14d",
    "holiday_count_next_7",
    "payday_cluster_flag",
        "event_uplift",
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
    
    # Hitung ulang target berdasarkan business rule.
    # Jika sisa_pagu < ratas_harian → ATM habis hari ini (0 hari).
    # Jika sisa_pagu >= ratas_harian → int(sisa_pagu / ratas_harian) - 1.
    _raw = (
        (df["sisa_pagu"] /
         df["ratas_harian"].replace(0, np.nan))
        .fillna(0)
        .astype(float)
        .astype(int)
    )
    df["jumlah_hari_check"] = np.where(
        df["sisa_pagu"] < df["ratas_harian"],
        0,
        np.maximum(_raw - 1, 0),
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
    # SPLIT DATA PER TID BERDASARKAN WAKTU (TIME-SERIES SPLIT)
    # ==========================================================
    # Data ATM bersifat temporal, sehingga split acak tidak ideal.
    # Kita urutkan tiap terminal berdasarkan updated dan ambil 80% awal
    # untuk train serta 20% terakhir untuk test, menjaga urutan waktu.
    df_ml = df_ml.sort_values(["tid", DT_COL]).reset_index(drop=True)

    train_frames = []
    test_frames = []

    for tid, group in df_ml.groupby("tid", sort=False):
        group = group.sort_values(DT_COL).copy()
        if len(group) < 2:
            train_frames.append(group)
            continue

        cutoff = max(1, int(len(group) * 0.8))
        train_frames.append(group.iloc[:cutoff])
        if len(group) > cutoff:
            test_frames.append(group.iloc[cutoff:])

    if not test_frames:
        raise ValueError(
            "Tidak cukup data per TID untuk melakukan time-series split. "
            "Pastikan tiap terminal memiliki minimal 2 record waktu yang cukup."
        )

    train_df = pd.concat(train_frames, ignore_index=True)
    test_df = pd.concat(test_frames, ignore_index=True)

    X_train = train_df[FITUR_ML]
    y_train = train_df[TARGET]
    X_test = test_df[FITUR_ML]
    y_test = test_df[TARGET]

    # ==========================================================
    # SCALING
    # ==========================================================
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    # ==========================================================
    # TRAINING
    # ==========================================================
    # Prepare sample weights (emphasize event windows)
    if "sample_weight_event" in df_ml.columns:
        sample_weights = df_ml.loc[X_train.index, "sample_weight_event"].values
    else:
        sample_weights = None

    # Try LightGBM first (supports sample_weight), fallback to RandomForest
    try:
        import lightgbm as lgb
        print("Menggunakan LightGBM untuk training (dengan sample weights jika tersedia)")
        model = lgb.LGBMRegressor(
            n_estimators=500,
            max_depth=8,
            learning_rate=0.05,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train_scaled, y_train, sample_weight=sample_weights)
        # feature importances from LGBM
        importances = model.feature_importances_
    except Exception:
        print("LightGBM tidak tersedia atau gagal, fallback ke RandomForest (sample_weight akan dipakai jika tersedia)")
        model = RandomForestRegressor(
            n_estimators=200,
            max_depth=8,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
        )
        if sample_weights is not None:
            model.fit(X_train_scaled, y_train, sample_weight=sample_weights)
        else:
            model.fit(X_train_scaled, y_train)
        importances = model.feature_importances_

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
    
    threshold_distribution = (
        pd.Series(y_pred, name='prediksi_hari')
        .apply(lambda v: status_from_hari(v))
        .value_counts()
        .to_dict()
    )

    eval_report = {
        "model_type": "rule_based_baseline",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dataset": {
            "train_rows": int(len(train_df)),
            "test_rows": int(len(test_df)),
            "tid_count": int(test_df["tid"].nunique()) if "tid" in test_df.columns else 0,
        },
        "metrics": {
            "mae_days": float(mae),
            "r2_score": float(r2),
            "mape_percent": float(mape),
        },
        "status_distribution": threshold_distribution,
        "rule_definition": {
            "kritis": "<= 1 hari",
            "waspada": "2 sampai 3 hari",
            "aman": "> 3 hari",
        },
    }

    save_rule_based_evaluation_report(eval_report)

    trend_report = {
        "model_type": "calendar_trend_model",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dataset": {
            "train_rows": int(len(train_df)),
            "test_rows": int(len(test_df)),
            "tid_count": int(test_df["tid"].nunique()) if "tid" in test_df.columns else 0,
        },
        "metrics": {
            "mae_days": float(mae),
            "r2_score": float(r2),
            "mape_percent": float(mape),
        },
        "status_distribution": threshold_distribution,
        "focus_features": [
            "is_weekend",
            "is_payday",
            "is_holiday",
            "days_to_payday",
            "days_since_payday",
            "is_near_holiday_3d",
            "trend_7d_ratio",
            "rolling_7d_ratio",
            "weekend_x_trend",
            "payday_x_trend",
            "holiday_x_trend",
        ],
        "event_pattern_summary": {
            "weekend": "weekend effect on demand and withdrawal pattern",
            "tanggal_merah": "holiday impact on ATM usage and liquidity pressure",
            "gajian": "payday effect on withdrawal intensity and cash depletion",
        },
    }
    save_calendar_trend_evaluation_report(trend_report)

    hybrid_report = {
        "model_type": "hybrid_rule_and_trend_model",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dataset": {
            "train_rows": int(len(train_df)),
            "test_rows": int(len(test_df)),
            "tid_count": int(test_df["tid"].nunique()) if "tid" in test_df.columns else 0,
        },
        "metrics": {
            "mae_days": float(mae),
            "r2_score": float(r2),
            "mape_percent": float(mape),
        },
        "status_distribution": threshold_distribution,
        "rule_definition": {
            "kritis": "<= 1 hari",
            "waspada": "2 sampai 3 hari",
            "aman": "> 3 hari",
        },
        "focus_features": [
            "sisa_pagu",
            "ratas_harian",
            "trend_7d_ratio",
            "rolling_7d_ratio",
            "is_weekend",
            "is_payday",
            "is_holiday",
            "days_to_payday",
            "days_since_payday",
            "weekend_x_trend",
            "payday_x_trend",
            "holiday_x_trend",
        ],
        "hybrid_summary": {
            "rule_based_signal": "status based on remaining balance and daily withdrawal rate",
            "trend_signal": "calendar and trend behavior from weekend, holiday, and payday effects",
            "combined_logic": "rule and trend are merged in the same feature set for final prediction",
        },
    }
    save_hybrid_rule_trend_evaluation_report(hybrid_report)

    # Feature importance
    feature_importance = pd.DataFrame({
        'feature': FITUR_ML,
        'importance': importances
    }).sort_values('importance', ascending=False)

    def categorize_feature(feature_name: str) -> str:
        name = feature_name.lower()
        if any(k in name for k in ["sisa_pagu", "ratas_harian", "selisih_lmb", "total_lmb", "pagu_existing"]):
            return "Balance & usage"
        if any(k in name for k in ["is_weekend", "is_payday", "is_holiday", "days_to_payday", "days_since_payday", "holiday_count_next_7", "payday_cluster_flag", "near_holiday"]):
            return "Calendar & event"
        if any(k in name for k in ["rolling_", "trend_", "cum_prev_", "event_uplift"]):
            return "Trend & history"
        if any(k in name for k in ["lag_", "weekday", "hari_", "bulan_", "kuartal", "tahun"]):
            return "Temporal & lag"
        if any(k in name for k in ["weekend_x_", "payday_x_", "holiday_x_", "sample_weight_event"]):
            return "Interaction features"
        return "Other"

    feature_importance["group"] = feature_importance["feature"].apply(categorize_feature)

    top20 = feature_importance.head(20).sort_values("importance", ascending=True)
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.barh(top20["feature"], top20["importance"], color=sns.color_palette("viridis", len(top20)))
    ax.invert_yaxis()
    ax.set_title("Feature Importance — Top 20")
    ax.set_xlabel("Importance")
    ax.set_ylabel("Feature")
    fig.tight_layout()
    fig.savefig(VISUALIZATION_DIR / "06_feature_importance_top20.png", dpi=200)
    plt.close(fig)

    group_summary = (
        feature_importance.groupby("group", as_index=False)["importance"].sum()
        .sort_values("importance", ascending=False)
    )
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=group_summary, x="importance", y="group", palette="viridis", ax=ax)
    ax.set_title("Feature Importance by Group")
    ax.set_xlabel("Total Importance")
    ax.set_ylabel("Feature Group")
    fig.tight_layout()
    fig.savefig(VISUALIZATION_DIR / "07_feature_importance_by_group.png", dpi=200)
    plt.close(fig)

    print("\nTOP 5 FEATURE IMPORTANCE:")
    print(feature_importance.head(5).to_string(index=False))
    print(f"\nVisualisasi feature importance disimpan di: {VISUALIZATION_DIR}")
    print(f"Laporan evaluasi rule-based disimpan di: {REPORTS_DIR}")

    return model, scaler


def save_rule_based_evaluation_report(report: dict) -> None:
    """Simpan laporan evaluasi rule-based dalam format JSON dan Markdown."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"rule_based_evaluation_{timestamp}.json"
    markdown_path = REPORTS_DIR / f"rule_based_evaluation_{timestamp}.md"

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    metrics = report["metrics"]
    dist = report["status_distribution"]
    md = f"""# Evaluasi Baseline Rule-Based ATM

- Tanggal: {report['generated_at']}
- Tipe model: {report['model_type']}
- Data train: {report['dataset']['train_rows']} baris
- Data test: {report['dataset']['test_rows']} baris
- TID uji: {report['dataset']['tid_count']}

## Aturan status

- Kritis: <= 1 hari
- Waspada: 2 sampai 3 hari
- Aman: > 3 hari

## Metrik evaluasi

- MAE: {metrics['mae_days']:.2f} hari
- R\u00b2: {metrics['r2_score']:.4f}
- MAPE: {metrics['mape_percent']:.2f}%

## Distribusi status hasil prediksi

```json
{json.dumps(dist, ensure_ascii=False, indent=2)}
```
"""
    markdown_path.write_text(md, encoding="utf-8")

    print(f"✅ Laporan JSON: {report_path}")
    print(f"✅ Laporan Markdown: {markdown_path}")
    return report_path


def save_calendar_trend_evaluation_report(report: dict) -> None:
    """Simpan laporan khusus untuk model berbasis kalender/tren seperti weekend, tanggal merah, gajian."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"trend_calendar_event_evaluation_{timestamp}.json"
    markdown_path = REPORTS_DIR / f"trend_calendar_event_evaluation_{timestamp}.md"

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    metrics = report["metrics"]
    dist = report["status_distribution"]
    focus = report["focus_features"]
    pattern_summary = report["event_pattern_summary"]
    md = f"""# Evaluasi Model Trend & Kalender ATM

- Tanggal: {report['generated_at']}
- Tipe model: {report['model_type']}
- Data train: {report['dataset']['train_rows']} baris
- Data test: {report['dataset']['test_rows']} baris
- TID uji: {report['dataset']['tid_count']}

## Fokus fitur

- {focus[0]}
- {focus[1]}
- {focus[2]}
- {focus[3]}
- {focus[4]}
- {focus[5]}
- {focus[6]}
- {focus[7]}
- {focus[8]}
- {focus[9]}
- {focus[10]}

## Pola tren yang dipertimbangkan

- Weekend: {pattern_summary['weekend']}
- Tanggal merah: {pattern_summary['tanggal_merah']}
- Gajian: {pattern_summary['gajian']}

## Metrik evaluasi

- MAE: {metrics['mae_days']:.2f} hari
- R\u00b2: {metrics['r2_score']:.4f}
- MAPE: {metrics['mape_percent']:.2f}%

## Distribusi status hasil prediksi

```json
{json.dumps(dist, ensure_ascii=False, indent=2)}
```
"""
    markdown_path.write_text(md, encoding="utf-8")

    print(f"✅ Laporan JSON model tren: {report_path}")
    print(f"✅ Laporan Markdown model tren: {markdown_path}")
    return report_path


def save_hybrid_rule_trend_evaluation_report(report: dict) -> None:
    """Simpan laporan gabungan rule-based dan trend/calendar dalam satu model."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"hybrid_rule_trend_evaluation_{timestamp}.json"
    markdown_path = REPORTS_DIR / f"hybrid_rule_trend_evaluation_{timestamp}.md"

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    metrics = report["metrics"]
    dist = report["status_distribution"]
    focus = report["focus_features"]
    hybrid = report["hybrid_summary"]
    md = f"""# Evaluasi Model Gabungan Rule-Based + Trend ATM

- Tanggal: {report['generated_at']}
- Tipe model: {report['model_type']}
- Data train: {report['dataset']['train_rows']} baris
- Data test: {report['dataset']['test_rows']} baris
- TID uji: {report['dataset']['tid_count']}

## Kombinasi sinyal

- Rule-based signal: {hybrid['rule_based_signal']}
- Trend signal: {hybrid['trend_signal']}
- Combined logic: {hybrid['combined_logic']}

## Fokus fitur utama

- {focus[0]}
- {focus[1]}
- {focus[2]}
- {focus[3]}
- {focus[4]}
- {focus[5]}
- {focus[6]}
- {focus[7]}
- {focus[8]}
- {focus[9]}
- {focus[10]}
- {focus[11]}

## Metrik evaluasi

- MAE: {metrics['mae_days']:.2f} hari
- R\u00b2: {metrics['r2_score']:.4f}
- MAPE: {metrics['mape_percent']:.2f}%

## Distribusi status hasil prediksi

```json
{json.dumps(dist, ensure_ascii=False, indent=2)}
```
"""
    markdown_path.write_text(md, encoding="utf-8")

    print(f"✅ Laporan JSON hybrid: {report_path}")
    print(f"✅ Laporan Markdown hybrid: {markdown_path}")
    return report_path


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
    
    # Tambahkan threshold berdasarkan status operasional yang konsisten
    df_terbaru["prediksi_hari"] = pd.to_numeric(
        df_terbaru["prediksi_hari"], errors="coerce"
    ).fillna(0)
    df_terbaru["threshold"] = df_terbaru["prediksi_hari"].apply(status_from_hari)

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