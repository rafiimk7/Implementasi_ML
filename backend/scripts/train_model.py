#!/usr/bin/env python
"""
Training Model ML — Prediksi Tanggal Habis ATM
------------------------------------------------

Pipeline:
1. Membaca data dari tabel `preprocessing`
2. Validasi target `jumlah_hari`
3. Cleaning missing value
4. Handling outlier
5. Time-series split per TID
6. Training LightGBM
   - fallback RandomForest
7. Evaluasi:
   - MAE
   - RMSE
   - R²
   - Median Absolute Error
   - MAPE
   - Error tolerance <= 1, 2, 3 hari
8. Perbandingan dengan Business Rule Baseline
9. Feature importance
10. Prediksi data terbaru setiap TID
11. Simpan hasil ke `hasil_prediksi`
12. Simpan model, scaler/feature metadata, dan evaluation report

CATATAN:
Model ini merupakan REGRESSION MODEL.

Target:
    jumlah_hari

Business Rule Baseline:
    jika sisa_pagu < ratas_harian:
        jumlah_hari = 0
    else:
        jumlah_hari = floor(sisa_pagu / ratas_harian) - 1

PENTING:
Target tidak otomatis diganti oleh business rule.
Business rule hanya digunakan sebagai BASELINE pembanding.
"""

import json
import os
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

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    median_absolute_error,
    r2_score,
)
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")


# ==========================================================
# PATH & KONFIGURASI
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

MODELS_DIR = PROJECT_ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

VISUALIZATION_DIR = PROJECT_ROOT / "visualizations"
VISUALIZATION_DIR.mkdir(parents=True, exist_ok=True)

REPORTS_DIR = VISUALIZATION_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(PROJECT_ROOT))


# ==========================================================
# IMPORT PROJECT
# ==========================================================

from config.config import get_db_engine
from scripts.predict_realtime import status_from_hari


# ==========================================================
# DATABASE CONFIG
# ==========================================================

PREPROCESS_TABLE = "preprocessing"
PREDICTION_TABLE = "hasil_prediksi"

DT_COL = "updated"
TARGET = "jumlah_hari"


# ==========================================================
# FITUR MODEL
# ==========================================================

FITUR_ML = [
    # Balance & Usage
    "sisa_pagu",
    "ratas_harian",
    "selisih_lmb",

    # Kalender Dasar
    "hari",
    "bulan",
    "tahun",
    "hari_ke",
    "kuartal",

    # Cyclic Encoding
    "hari_sin",
    "hari_cos",
    "bulan_sin",
    "bulan_cos",
    "hari_ke_sin",
    "hari_ke_cos",

    # Kalender Cerdas
    "is_weekend",
    "is_payday",
    "is_holiday",
    "days_to_payday",
    "days_since_payday",
    "is_near_holiday_3d",

    # Trend Historis
    "rolling_7d",
    "rolling_14d",
    "rolling_30d",
    "rolling_std_7d",
    "rolling_std_14d",
    "rolling_7d_ratio",
    "trend_7d_ratio",
    "trend_14d_ratio",

    # Interaction Features
    "weekend_x_ratas_harian",
    "payday_x_sisa_pagu",
    "holiday_x_ratas_harian",
    "weekend_x_trend",
    "payday_x_trend",
    "holiday_x_trend",

    # Lag & Weekday
    "lag_1_ratas",
    "lag_7_ratas",
    "lag_14_ratas",
    "lag_7_sisa_pagu",
    "weekday_sin",
    "weekday_cos",
    "payday_x_weekday_sin",
    "weekend_x_rolling_std_7d",

    # Event / Window
    "cum_prev_3d",
    "cum_prev_7d",
    "cum_prev_14d",
    "holiday_count_next_7",
    "payday_cluster_flag",
    "event_uplift",
]


# ==========================================================
# MODEL CONFIGURATION
# ==========================================================

LIGHTGBM_CONFIG = {
    "objective": "regression",
    "n_estimators": 500,
    "learning_rate": 0.05,
    "max_depth": 8,
    "num_leaves": 31,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "n_jobs": -1,
    "verbosity": -1,
}


RANDOM_FOREST_CONFIG = {
    "n_estimators": 300,
    "max_depth": 10,
    "min_samples_split": 10,
    "min_samples_leaf": 5,
    "max_features": "sqrt",
    "random_state": 42,
    "n_jobs": -1,
}


# ==========================================================
# 1. LOAD DATA
# ==========================================================

def load_preprocessing() -> pd.DataFrame:
    print("=" * 70)
    print("LOAD DATA DARI TABEL PREPROCESSING")
    print("=" * 70)

    engine = get_db_engine()

    query = f"""
        SELECT *
        FROM {PREPROCESS_TABLE}
    """

    df = pd.read_sql(query, con=engine)

    print(f"Data berhasil dimuat : {len(df):,} baris")
    print(f"Jumlah kolom         : {len(df.columns)}")

    # Validasi kolom
    kolom_wajib = FITUR_ML + [TARGET, "tid", DT_COL]

    kolom_kurang = [
        kolom for kolom in kolom_wajib
        if kolom not in df.columns
    ]

    if kolom_kurang:
        raise ValueError(
            "Kolom wajib tidak ditemukan:\n"
            + "\n".join(f"- {kolom}" for kolom in kolom_kurang)
        )

    # Datetime
    df[DT_COL] = pd.to_datetime(df[DT_COL], errors="coerce")

    # Buang datetime invalid
    invalid_datetime = df[DT_COL].isna().sum()

    if invalid_datetime > 0:
        print(
            f"[WARNING] {invalid_datetime} record memiliki "
            f"datetime invalid dan akan dihapus."
        )
        df = df.dropna(subset=[DT_COL])

    # Tanggal
    df["tanggal"] = df[DT_COL].dt.date

    return df


# ==========================================================
# 2. VALIDASI TARGET
# ==========================================================

def validate_target(df: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 70)
    print("VALIDASI TARGET")
    print("=" * 70)

    # Business Rule
    ratio = df["sisa_pagu"] / df["ratas_harian"].replace(0, np.nan)

    jumlah_hari_check = np.where(
        df["sisa_pagu"] < df["ratas_harian"],
        0,
        np.maximum(np.floor(ratio.fillna(0)) - 1, 0)
    )

    jumlah_hari_check = pd.Series(
        jumlah_hari_check,
        index=df.index
    ).astype(float)

    # Target asli
    target_numeric = pd.to_numeric(df[TARGET], errors="coerce")

    valid_target = target_numeric.notna()

    df[TARGET] = target_numeric

    # Konsistensi
    konsisten = (
        df.loc[valid_target, TARGET]
        ==
        jumlah_hari_check.loc[valid_target]
    )

    if len(konsisten) > 0:
        konsisten_pct = konsisten.mean() * 100
    else:
        konsisten_pct = 0

    print(f"Target valid        : {valid_target.sum():,}")
    print(f"Target invalid      : {(~valid_target).sum():,}")
    print(f"Konsistensi dengan business rule : {konsisten_pct:.2f}%")

    if konsisten_pct < 95:
        print("\n[INFO] Target berbeda dengan business rule.")
        print("[INFO] Target ASLI tetap digunakan untuk training.")
    else:
        print("\n[INFO] Sebagian besar target konsisten dengan business rule.")

    return df


# ==========================================================
# 3. CLEANING DATA
# ==========================================================

def clean_training_data(df: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 70)
    print("CLEANING DATA TRAINING")
    print("=" * 70)

    df_ml = df.copy()

    # Target valid
    df_ml = df_ml[df_ml[TARGET].notna()].copy()

    # Rata-rata harian valid
    df_ml = df_ml[
        df_ml["ratas_harian"].notna()
        & (df_ml["ratas_harian"] > 0)
    ].copy()

    # Target >= 0
    df_ml = df_ml[df_ml[TARGET] >= 0].copy()

    # Sort
    df_ml = (
        df_ml
        .sort_values(["tid", DT_COL])
        .reset_index(drop=True)
    )

    # Missing value
    print("\nMissing value:")
    total_missing = 0

    for col in FITUR_ML:
        missing_before = df_ml[col].isna().sum()
        total_missing += missing_before

        if df_ml[col].isna().all():
            df_ml[col] = 0
        else:
            median_value = df_ml[col].median()
            df_ml[col] = df_ml[col].fillna(median_value)

    print(f"Total missing feature yang ditangani: {total_missing:,}")

    # Outlier
    print("\nWinsorization:")

    for col in ["selisih_lmb", "ratas_harian"]:
        if col not in df_ml.columns:
            continue

        lower = df_ml[col].quantile(0.01)
        upper = df_ml[col].quantile(0.99)

        df_ml[col] = df_ml[col].clip(lower=lower, upper=upper)

        print(f"{col}: {lower:.2f} - {upper:.2f}")

    print(f"\nJumlah data setelah cleaning : {len(df_ml):,}")
    print(f"Jumlah TID                  : {df_ml['tid'].nunique():,}")

    if len(df_ml) < 20:
        raise ValueError("Data terlalu sedikit untuk training.")

    return df_ml


# ==========================================================
# 4. TIME SERIES SPLIT PER TID
# ==========================================================

def time_series_split(df: pd.DataFrame):
    print("\n" + "=" * 70)
    print("TIME-SERIES SPLIT PER TID")
    print("=" * 70)

    train_frames = []
    test_frames = []
    skipped_tid = []

    for tid, group in df.groupby("tid", sort=False):
        group = group.sort_values(DT_COL).copy()

        # Minimal 5 record
        if len(group) < 5:
            skipped_tid.append((tid, len(group)))
            continue

        cutoff = int(len(group) * 0.80)
        cutoff = max(cutoff, 1)

        train_part = group.iloc[:cutoff].copy()
        test_part = group.iloc[cutoff:].copy()

        if len(test_part) == 0:
            continue

        train_frames.append(train_part)
        test_frames.append(test_part)

    if not train_frames:
        raise ValueError("Tidak ada data training.")

    if not test_frames:
        raise ValueError("Tidak ada data testing.")

    train_df = pd.concat(train_frames, ignore_index=True)
    test_df = pd.concat(test_frames, ignore_index=True)

    print(f"Train rows : {len(train_df):,}")
    print(f"Test rows  : {len(test_df):,}")
    print(f"Train TID  : {train_df['tid'].nunique():,}")
    print(f"Test TID   : {test_df['tid'].nunique():,}")
    print(
        f"Train ratio: "
        f"{len(train_df) / (len(train_df) + len(test_df)) * 100:.2f}%"
    )
    print(
        f"Test ratio : "
        f"{len(test_df) / (len(train_df) + len(test_df)) * 100:.2f}%"
    )

    if skipped_tid:
        print("\n[INFO] TID yang dilewati karena data < 5:")
        for tid, count in skipped_tid[:10]:
            print(f"  TID {tid}: {count} record")
        if len(skipped_tid) > 10:
            print(f"  ... dan {len(skipped_tid) - 10} TID lainnya.")

    return train_df, test_df


# ==========================================================
# 5. TRAIN MODEL
# ==========================================================

def train_model(X_train, y_train, sample_weights=None):
    print("\n" + "=" * 70)
    print("TRAINING MODEL")
    print("=" * 70)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)

    # LIGHTGBM
    try:
        import lightgbm as lgb

        print("\n[MODEL] LightGBM Regressor")
        print("Parameter:")
        for key, value in LIGHTGBM_CONFIG.items():
            print(f"  {key}: {value}")

        model = lgb.LGBMRegressor(**LIGHTGBM_CONFIG)

        if sample_weights is not None:
            model.fit(X_train_scaled, y_train, sample_weight=sample_weights)
        else:
            model.fit(X_train_scaled, y_train)

        return model, scaler, "LightGBM"

    except Exception as e:
        print(f"\n[WARNING] LightGBM gagal: {e}")
        print("\n[MODEL] RandomForestRegressor")
        print("Parameter:")
        for key, value in RANDOM_FOREST_CONFIG.items():
            print(f"  {key}: {value}")

        model = RandomForestRegressor(**RANDOM_FOREST_CONFIG)

        if sample_weights is not None:
            model.fit(X_train_scaled, y_train, sample_weight=sample_weights)
        else:
            model.fit(X_train_scaled, y_train)

        return model, scaler, "RandomForest"


# ==========================================================
# 6. BUSINESS RULE BASELINE
# ==========================================================

def calculate_business_rule(df: pd.DataFrame):
    ratio = df["sisa_pagu"] / df["ratas_harian"].replace(0, np.nan)

    baseline = np.where(
        df["sisa_pagu"] < df["ratas_harian"],
        0,
        np.maximum(np.floor(ratio.fillna(0)) - 1, 0)
    )

    return np.asarray(baseline, dtype=float)


# ==========================================================
# 7. CALCULATE REGRESSION METRICS
# ==========================================================

def calculate_metrics(y_true, y_pred):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    # MAE
    mae = mean_absolute_error(y_true, y_pred)

    # RMSE
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))

    # R2
    if len(y_true) > 1:
        r2 = r2_score(y_true, y_pred)
    else:
        r2 = np.nan

    # Median Absolute Error
    median_ae = median_absolute_error(y_true, y_pred)

    # MAPE
    mask = y_true != 0
    if mask.sum() > 0:
        mape = (
            np.mean(
                np.abs(
                    (y_true[mask] - y_pred[mask]) / y_true[mask]
                )
            )
            * 100
        )
    else:
        mape = np.nan

    # Error
    abs_error = np.abs(y_true - y_pred)

    within_1_day = (abs_error <= 1).mean() * 100
    within_2_days = (abs_error <= 2).mean() * 100
    within_3_days = (abs_error <= 3).mean() * 100

    return {
        "mae_days": float(mae),
        "rmse_days": float(rmse),
        "r2": float(r2),
        "median_absolute_error_days": float(median_ae),
        "mape_percent": float(mape),
        "within_1_day_percent": float(within_1_day),
        "within_2_days_percent": float(within_2_days),
        "within_3_days_percent": float(within_3_days),
    }


# ==========================================================
# 8. EVALUATION
# ==========================================================

def evaluate_model(model, scaler, model_name, train_df, test_df):
    print("\n" + "=" * 70)
    print("EVALUASI MODEL")
    print("=" * 70)

    X_train = train_df[FITUR_ML].copy()
    y_train = train_df[TARGET].astype(float)

    X_test = test_df[FITUR_ML].copy()
    y_test = test_df[TARGET].astype(float)

    # Prediction
    X_test_scaled = scaler.transform(X_test)
    y_pred = model.predict(X_test_scaled)

    # Hari tidak boleh negatif
    y_pred = np.maximum(y_pred, 0)

    # ML Metrics
    ml_metrics = calculate_metrics(y_test, y_pred)

    # Baseline
    baseline_pred = calculate_business_rule(test_df)
    baseline_metrics = calculate_metrics(y_test, baseline_pred)

    # Print
    print(f"\nModel: {model_name}")

    print("\n" + "-" * 50)
    print("METRIK MODEL ML")
    print("-" * 50)

    print(f"MAE       : {ml_metrics['mae_days']:.4f} hari")
    print(f"RMSE      : {ml_metrics['rmse_days']:.4f} hari")
    print(f"R²        : {ml_metrics['r2']:.4f}")
    print(
        f"Median AE : "
        f"{ml_metrics['median_absolute_error_days']:.4f} hari"
    )
    print(f"MAPE      : {ml_metrics['mape_percent']:.2f}%")
    print(
        f"Error <=1 hari : "
        f"{ml_metrics['within_1_day_percent']:.2f}%"
    )
    print(
        f"Error <=2 hari : "
        f"{ml_metrics['within_2_days_percent']:.2f}%"
    )
    print(
        f"Error <=3 hari : "
        f"{ml_metrics['within_3_days_percent']:.2f}%"
    )

    print("\n" + "-" * 50)
    print("BUSINESS RULE BASELINE")
    print("-" * 50)

    print(f"MAE       : {baseline_metrics['mae_days']:.4f} hari")
    print(f"RMSE      : {baseline_metrics['rmse_days']:.4f} hari")
    print(f"R²        : {baseline_metrics['r2']:.4f}")

    # Improvement
    if baseline_metrics["mae_days"] > 0:
        mae_improvement = (
            (baseline_metrics["mae_days"] - ml_metrics["mae_days"])
            / baseline_metrics["mae_days"]
            * 100
        )
    else:
        mae_improvement = 0

    print("\n" + "-" * 50)
    print("PERBANDINGAN MAE")
    print("-" * 50)

    print(f"Baseline MAE : {baseline_metrics['mae_days']:.4f}")
    print(f"ML MAE       : {ml_metrics['mae_days']:.4f}")
    print(f"Perubahan    : {mae_improvement:.2f}%")

    # Status distribution
    status_distribution = (
        pd.Series(y_pred)
        .apply(lambda x: status_from_hari(x))
        .value_counts()
        .to_dict()
    )

    return {
        "model_metrics": ml_metrics,
        "baseline_metrics": baseline_metrics,
        "mae_improvement_percent": float(mae_improvement),
        "status_distribution": status_distribution,
        "y_test": y_test,
        "y_pred": y_pred,
        "baseline_pred": baseline_pred,
    }


# ==========================================================
# 9. FEATURE IMPORTANCE
# ==========================================================

def save_feature_importance(model, model_name):
    if not hasattr(model, "feature_importances_"):
        print(
            "[WARNING] Model tidak menyediakan feature importance."
        )
        return None

    feature_importance = pd.DataFrame({
        "feature": FITUR_ML,
        "importance": model.feature_importances_
    })

    feature_importance = (
        feature_importance
        .sort_values("importance", ascending=False)
        .reset_index(drop=True)
    )

    # Print
    print("\n" + "=" * 70)
    print("TOP 20 FEATURE IMPORTANCE")
    print("=" * 70)

    print(feature_importance.head(20).to_string(index=False))

    # CSV
    csv_path = REPORTS_DIR / "feature_importance.csv"
    feature_importance.to_csv(csv_path, index=False)

    # Visualization
    top20 = (
        feature_importance
        .head(20)
        .sort_values("importance", ascending=True)
    )

    fig, ax = plt.subplots(figsize=(10, 8))

    ax.barh(top20["feature"], top20["importance"])

    ax.set_title(f"Feature Importance - {model_name}")
    ax.set_xlabel("Importance")
    ax.set_ylabel("Feature")

    fig.tight_layout()

    image_path = (
        VISUALIZATION_DIR / "06_feature_importance_top20.png"
    )

    fig.savefig(image_path, dpi=200)
    plt.close(fig)

    print(f"\nFeature importance CSV: {csv_path}")
    print(f"Feature importance image: {image_path}")

    return feature_importance


# ==========================================================
# 10. SAVE MODEL KE FOLDER backend/models
# ==========================================================


def save_models(model, scaler) -> None:
    """Simpan model, scaler, dan daftar fitur ke folder backend/models."""
    model_path = MODELS_DIR / "model_prediksi_habis.pkl"
    scaler_path = MODELS_DIR / "scaler.pkl"
    fitur_path = MODELS_DIR / "fitur.pkl"

    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    joblib.dump(FITUR_ML, fitur_path)

    print("\n✅ Model disimpan ke folder backend/models:")
    print(f"  - {model_path}")
    print(f"  - {scaler_path}")
    print(f"  - {fitur_path}")


# ==========================================================
# 11. SAVE EVALUATION REPORT
# ==========================================================

def save_evaluation_report(evaluation, model_name, train_df, test_df):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model": {
            "name": model_name,
            "type": "regression",
            "target": TARGET,
            "random_state": 42,
        },
        "dataset": {
            "total_rows": int(len(train_df) + len(test_df)),
            "train_rows": int(len(train_df)),
            "test_rows": int(len(test_df)),
            "train_tid": int(train_df["tid"].nunique()),
            "test_tid": int(test_df["tid"].nunique()),
        },
        "features": {
            "count": len(FITUR_ML),
            "names": FITUR_ML,
        },
        "split": {
            "method": "time_series_split_per_tid",
            "train_ratio": 0.80,
            "test_ratio": 0.20,
        },
        "parameters": (
            LIGHTGBM_CONFIG
            if model_name == "LightGBM"
            else RANDOM_FOREST_CONFIG
        ),
        "metrics": {
            "model": evaluation["model_metrics"],
            "business_rule_baseline": evaluation["baseline_metrics"],
            "mae_improvement_percent": evaluation["mae_improvement_percent"],
        },
        "error_tolerance": {
            "within_1_day_percent": evaluation["model_metrics"]["within_1_day_percent"],
            "within_2_days_percent": evaluation["model_metrics"]["within_2_days_percent"],
            "within_3_days_percent": evaluation["model_metrics"]["within_3_days_percent"],
        },
        "status_distribution": evaluation["status_distribution"],
        "baseline_definition": {
            "condition": "sisa_pagu < ratas_harian",
            "result": "0 hari",
            "formula": "floor(sisa_pagu / ratas_harian) - 1",
        },
    }

    json_path = REPORTS_DIR / f"model_evaluation_{timestamp}.json"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    latest_path = REPORTS_DIR / "model_evaluation_latest.json"

    with latest_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Markdown
    metrics = evaluation["model_metrics"]
    baseline = evaluation["baseline_metrics"]

    md = f"""
# Evaluasi Model Prediksi Tanggal Habis ATM

## Model

- Nama model: {model_name}
- Tipe: Regression
- Target: `{TARGET}`

## Dataset

- Total data: {len(train_df) + len(test_df):,}
- Training: {len(train_df):,}
- Testing: {len(test_df):,}
- TID training: {train_df['tid'].nunique():,}
- TID testing: {test_df['tid'].nunique():,}

## Metode Split

Time-Series Split per TID.

- Training: 80%
- Testing: 20%

Data testing merupakan periode waktu setelah data training pada masing-masing TID.

## Parameter Model

```text
{json.dumps(
    LIGHTGBM_CONFIG
    if model_name == "LightGBM"
    else RANDOM_FOREST_CONFIG,
    indent=2,
)}
```

## Hasil Evaluasi

| Metrik | Nilai |
| --- | ---: |
| MAE | {metrics['mae_days']:.4f} hari |
| RMSE | {metrics['rmse_days']:.4f} hari |
| R² | {metrics['r2']:.4f} |
| Median AE | {metrics['median_absolute_error_days']:.4f} hari |
| MAPE | {metrics['mape_percent']:.2f}% |
| Error <= 1 hari | {metrics['within_1_day_percent']:.2f}% |
| Error <= 2 hari | {metrics['within_2_days_percent']:.2f}% |
| Error <= 3 hari | {metrics['within_3_days_percent']:.2f}% |

## Baseline Bisnis

| Metrik | Nilai |
| --- | ---: |
| MAE | {baseline['mae_days']:.4f} hari |
| RMSE | {baseline['rmse_days']:.4f} hari |
| R² | {baseline['r2']:.4f} |

## Perubahan MAE

- Baseline MAE: {baseline['mae_days']:.4f}
- Model MAE: {metrics['mae_days']:.4f}
- Perubahan: {evaluation['mae_improvement_percent']:.2f}%

## Status Distribusi

```text
{json.dumps(evaluation['status_distribution'], indent=2, ensure_ascii=False)}
```
"""

    md_path = REPORTS_DIR / f"model_evaluation_{timestamp}.md"
    latest_md_path = REPORTS_DIR / "model_evaluation_latest.md"

    md_path.write_text(md, encoding="utf-8")
    latest_md_path.write_text(md, encoding="utf-8")

    print(f"\nEvaluation JSON: {json_path}")
    print(f"Evaluation markdown: {md_path}")

    return {
        "json_path": str(json_path),
        "markdown_path": str(md_path),
    }


# ==========================================================
# 12. MAIN
# ==========================================================


def main():
    print("=" * 70)
    print("TRAINING MODEL PREDIKSI TANGGAL HABIS ATM")
    print("=" * 70)

    df = load_preprocessing()
    df = validate_target(df)
    df = clean_training_data(df)

    train_df, test_df = time_series_split(df)

    X_train = train_df[FITUR_ML].copy()
    y_train = train_df[TARGET].astype(float)

    model, scaler, model_name = train_model(X_train, y_train)
    evaluation = evaluate_model(model, scaler, model_name, train_df, test_df)

    save_feature_importance(model, model_name)
    save_models(model, scaler)
    save_evaluation_report(evaluation, model_name, train_df, test_df)

    print("\n" + "=" * 70)
    print("✅ TRAINING SELESAI")
    print("=" * 70)


if __name__ == "__main__":
    main()
