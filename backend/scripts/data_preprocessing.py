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
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import BigInteger, Date, DateTime, Float, Integer, SmallInteger, String

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

# Tambahkan root project dan folder scripts ke sys.path agar config + helper lokal bisa diimport
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
SCRIPTS_DIR = os.path.dirname(__file__)
for p in [PROJECT_ROOT, SCRIPTS_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from config.config import get_db_engine
try:
    from calendar_features import add_calendar_flags, get_holidays, get_payday_date
except ModuleNotFoundError:  # fallback saat file di-import dari package scripts/
    from scripts.calendar_features import add_calendar_flags, get_holidays, get_payday_date

# ==========================================================
# KONFIGURASI
# ==========================================================

SOURCE_TABLE = os.getenv("SOURCE_TABLE", "data_2026")  # tabel sumber (bisa di-override via env var)
OUTPUT_TABLE = "preprocessing"  # tabel hasil preprocessing
DT_COL       = "updated"        # kolom datetime utama

# Konfigurasi fitur kalender cerdas
PAYDAY_DATE          = os.getenv("PAYDAY_DATE", "25")           # "25" atau "last_workday"
CALENDARIFIC_API_KEY = os.getenv("CALENDARIFIC_API_KEY", "ix341jES8qMP90wDJkUz3u0KFWryqa47")    # API key dari calendarific.com
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

    # Rolling standard deviation and longer window
    df_harian["rolling_std_7d"] = (
        df_harian.groupby("tid")["selisih_lmb"]
        .transform(lambda s: s.shift(1).rolling(window=7, min_periods=1).std())
    ).fillna(0.0)

    df_harian["rolling_std_14d"] = (
        df_harian.groupby("tid")["selisih_lmb"]
        .transform(lambda s: s.shift(1).rolling(window=14, min_periods=1).std())
    ).fillna(0.0)

    df_harian["rolling_30d"] = (
        df_harian.groupby("tid")["selisih_lmb"]
        .transform(lambda s: s.shift(1).rolling(window=30, min_periods=1).mean())
    )

    # Lag features for rata & sisa_pagu (helps capture recent seasonal shifts)
    df_harian["lag_1_ratas"] = (
        df_harian.groupby("tid")["ratas_harian"].shift(1)
    ).fillna(0).astype(int)
    df_harian["lag_7_ratas"] = (
        df_harian.groupby("tid")["ratas_harian"].shift(7)
    ).fillna(0).astype(int)
    df_harian["lag_14_ratas"] = (
        df_harian.groupby("tid")["ratas_harian"].shift(14)
    ).fillna(0).astype(int)

    df_harian["lag_7_sisa_pagu"] = (
        df_harian.groupby("tid")["sisa_pagu"].shift(7)
    ).fillna(0).astype(int)

    # Rolling ratio: short-term vs medium-term
    df_harian["rolling_7d_ratio"] = (
        df_harian["rolling_7d"].replace(0, np.nan) / df_harian["rolling_14d"].replace(0, np.nan)
    ).fillna(1.0)

    df_harian["trend_7d_ratio"] = (
        df_harian["selisih_lmb"] / df_harian["rolling_7d"].replace(0, np.nan)
    ).fillna(1.0)

    df_harian["trend_14d_ratio"] = (
        df_harian["selisih_lmb"] / df_harian["rolling_14d"].replace(0, np.nan)
    ).fillna(1.0)

    # Cumulative previous windows (proxy for event-driven surge)
    df_harian["cum_prev_3d"] = (
        df_harian.groupby("tid")["selisih_lmb"]
        .transform(lambda s: s.shift(1).rolling(window=3, min_periods=1).sum())
    )
    df_harian["cum_prev_7d"] = (
        df_harian.groupby("tid")["selisih_lmb"]
        .transform(lambda s: s.shift(1).rolling(window=7, min_periods=1).sum())
    )
    df_harian["cum_prev_14d"] = (
        df_harian.groupby("tid")["selisih_lmb"]
        .transform(lambda s: s.shift(1).rolling(window=14, min_periods=1).sum())
    )

    # Holiday count in next 7 days (uses holiday_set from calendar features later)
    # placeholder zero; will be updated in feature_engineering where holiday_set is known
    df_harian["holiday_count_next_7"] = 0

    # Payday cluster: 1 if payday within +/-3 days
    df_harian["payday_cluster_flag"] = 0

    # Event uplift proxy: short-term vs long-term usage
    df_harian["event_uplift"] = df_harian["rolling_7d"] / df_harian["rolling_30d"].replace(0, np.nan)
    df_harian["event_uplift"] = df_harian["event_uplift"].replace([np.inf, -np.inf], np.nan).fillna(1.0)

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

    # -- Mingguan (weekday) cyclic encoding : periode 7 --
    df["weekday"] = df[DT_COL].dt.dayofweek  # 0 = Monday
    df["weekday_sin"] = np.sin(2 * np.pi * df["weekday"] / 7)
    df["weekday_cos"] = np.cos(2 * np.pi * df["weekday"] / 7)

    # -- Fitur kalender cerdas (flag + jarak ke gajian / libur) --
    df = add_calendar_flags(
        df,
        dt_col=DT_COL,
        engine=engine,
        payday_config=PAYDAY_DATE,
        api_key=CALENDARIFIC_API_KEY,
        country=HOLIDAY_COUNTRY,
    )

    # Update holiday_count_next_7 and payday_cluster_flag using calendar info
    if "is_holiday" in df.columns:
        # Compute holiday dates set per TID date row
        dt_ser = pd.to_datetime(df[DT_COL])
        df["holiday_count_next_7"] = dt_ser.apply(
            lambda t: sum(
                1 for i in range(1, 8)
                if (t.date() + pd.Timedelta(days=i)) in {
                    d for y in range(t.year, t.year + 2) for d in get_holidays(y, engine=engine, api_key=CALENDARIFIC_API_KEY, country=HOLIDAY_COUNTRY)
                }
            )
        )

    if "is_payday" in df.columns:
        dt_ser = pd.to_datetime(df[DT_COL])
        df["payday_cluster_flag"] = dt_ser.apply(
            lambda t: int(
                any(
                    abs((get_payday_date(dt.year, dt.month, PAYDAY_DATE) - t.date()).days) <= 3
                    for dt in [t.date(), (t + pd.Timedelta(days=1)).date(), (t - pd.Timedelta(days=1)).date()]
                )
            )
        )

    # Sample weight: emphasize event windows (payday or near holiday)
    df["sample_weight_event"] = 1.0 + (
        df.get("is_payday", 0).astype(int) * 2.0 + df.get("is_near_holiday_3d", 0).astype(int) * 1.5
    )

    # Interaction features: kalender + transaksi
    df["weekend_x_ratas_harian"] = df["is_weekend"] * df["ratas_harian"]
    df["payday_x_sisa_pagu"] = df["is_payday"] * df["sisa_pagu"]
    df["holiday_x_ratas_harian"] = df["is_holiday"] * df["ratas_harian"]

    # Event-trend interaction: feature event + trend historis
    df["weekend_x_trend"] = df["is_weekend"] * df["trend_7d_ratio"]
    df["payday_x_trend"] = df["is_payday"] * df["trend_7d_ratio"]
    df["holiday_x_trend"] = df["is_holiday"] * df["trend_7d_ratio"]

    # Additional seasonal interactions
    df["payday_x_weekday_sin"] = df["is_payday"] * df["weekday_sin"]
    df["weekend_x_rolling_std_7d"] = df["is_weekend"] * df["rolling_std_7d"]

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
# 4. VISUALISASI DATA
# ==========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VISUALIZATION_DIR = PROJECT_ROOT / "visualizations"
VISUALIZATION_DIR.mkdir(parents=True, exist_ok=True)


def generate_visualizations(df: pd.DataFrame, output_dir: Path = VISUALIZATION_DIR) -> None:
    """Menghasilkan visualisasi data untuk eksplorasi pola ATM dan fitur kalender."""
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_df = df.copy()

    if "tanggal" in plot_df.columns:
        plot_df["tanggal"] = pd.to_datetime(plot_df["tanggal"])

    # 1. Distribusi fitur utama
    dist_cols = [
        "selisih_lmb",
        "pagu_existing",
        "sisa_pagu",
        "ratas_harian",
        "jumlah_hari",
    ]
    dist_cols = [c for c in dist_cols if c in plot_df.columns]

    if dist_cols:
        fig, axes = plt.subplots(2, 3, figsize=(18, 10))
        axes = axes.flatten()
        for ax, col in zip(axes, dist_cols[:len(axes)]):
            sns.histplot(plot_df[col].dropna(), bins=30, kde=True, ax=ax)
            ax.set_title(f"Distribusi {col}")
            ax.set_xlabel(col)
            ax.set_ylabel("Frekuensi")
        for i in range(len(dist_cols), len(axes)):
            axes[i].axis("off")
        fig.tight_layout()
        fig.savefig(output_dir / "01_distribusi_fitur_utama.png", dpi=200)
        plt.close(fig)

    # 2. Trend agregat per tanggal
    if {"tanggal", "total_lmb", "sisa_pagu", "selisih_lmb"}.issubset(plot_df.columns):
        trend = (
            plot_df.groupby("tanggal", as_index=False)
            [["total_lmb", "sisa_pagu", "selisih_lmb"]]
            .mean()
            .sort_values("tanggal")
        )
        fig, axes = plt.subplots(3, 1, figsize=(18, 12), sharex=True)
        axes[0].plot(trend["tanggal"], trend["total_lmb"], marker="o", linewidth=1.8)
        axes[0].set_title("Rata-rata total_lmb per tanggal")
        axes[1].plot(trend["tanggal"], trend["sisa_pagu"], marker="o", linewidth=1.8, color="green")
        axes[1].set_title("Rata-rata sisa_pagu per tanggal")
        axes[2].plot(trend["tanggal"], trend["selisih_lmb"], marker="o", linewidth=1.8, color="orange")
        axes[2].set_title("Rata-rata selisih_lmb per tanggal")
        for ax in axes:
            ax.grid(True, linestyle="--", alpha=0.4)
        fig.tight_layout()
        fig.savefig(output_dir / "02_trend_per_tanggal.png", dpi=200)
        plt.close(fig)

    # 3. Distribusi event kalender
    event_cols = [
        "is_weekend",
        "is_payday",
        "is_holiday",
        "is_near_holiday_3d",
    ]
    event_cols = [c for c in event_cols if c in plot_df.columns]
    if event_cols:
        event_summary = pd.DataFrame({
            "kolom": event_cols,
            "jumlah": [int(plot_df[c].sum()) for c in event_cols],
        })
        fig, ax = plt.subplots(figsize=(10, 5))
        sns.barplot(data=event_summary, x="kolom", y="jumlah", palette="Set2", ax=ax)
        ax.set_title("Jumlah event kalender")
        ax.set_xlabel("Kolom fitur kalender")
        ax.set_ylabel("Jumlah kejadian")
        for label in ax.get_xticklabels():
            label.set_rotation(0)
        fig.tight_layout()
        fig.savefig(output_dir / "03_event_kalender.png", dpi=200)
        plt.close(fig)

    # 4. Correlation heatmap
    corr_cols = [
        "total_lmb",
        "selisih_lmb",
        "pagu_existing",
        "sisa_pagu",
        "ratas_harian",
        "jumlah_hari",
        "is_weekend",
        "is_payday",
        "is_holiday",
        "rolling_7d",
        "rolling_30d",
        "trend_7d_ratio",
    ]
    corr_cols = [c for c in corr_cols if c in plot_df.columns]
    if len(corr_cols) > 1:
        corr = plot_df[corr_cols].corr(numeric_only=True)
        fig, ax = plt.subplots(figsize=(12, 9))
        sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax)
        ax.set_title("Heatmap Korelasi Fitur Utama")
        fig.tight_layout()
        fig.savefig(output_dir / "04_heatmap_korelasi.png", dpi=200)
        plt.close(fig)

    # 5. Top-risk ATM by sisa pagu and jumlah_hari
    if {"tid", "sisa_pagu", "jumlah_hari"}.issubset(plot_df.columns):
        risk = (
            plot_df.groupby("tid", as_index=False)
            [["sisa_pagu", "jumlah_hari"]]
            .mean()
            .sort_values(["jumlah_hari", "sisa_pagu"], ascending=[False, True])
            .head(10)
        )
        fig, ax = plt.subplots(figsize=(12, 6))
        sns.barplot(data=risk, x="tid", y="jumlah_hari", palette="Reds_d", ax=ax)
        ax.set_title("10 ATM dengan prediksi hari paling panjang / paling kritis")
        ax.set_xlabel("TID")
        ax.set_ylabel("Jumlah hari")
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        fig.savefig(output_dir / "05_top_risk_atm.png", dpi=200)
        plt.close(fig)

    print(f"\nVisualisasi data disimpan di: {output_dir}")
    print("  - 01_distribusi_fitur_utama.png")
    print("  - 02_trend_per_tanggal.png")
    print("  - 03_event_kalender.png")
    print("  - 04_heatmap_korelasi.png")
    print("  - 05_top_risk_atm.png")


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
        "rolling_7d", "rolling_14d", "rolling_30d", "rolling_std_7d", "rolling_std_14d", "rolling_7d_ratio", "trend_7d_ratio", "trend_14d_ratio",
        "weekend_x_ratas_harian", "payday_x_sisa_pagu", "holiday_x_ratas_harian",
        "weekend_x_trend", "payday_x_trend", "holiday_x_trend",
        "lag_1_ratas", "lag_7_ratas", "lag_14_ratas", "lag_7_sisa_pagu",
        "weekday_sin", "weekday_cos", "payday_x_weekday_sin", "weekend_x_rolling_std_7d",
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

        # Additional event/window numeric columns
        for col in [
            "cum_prev_3d", "cum_prev_7d", "cum_prev_14d",
            "holiday_count_next_7", "payday_cluster_flag", "event_uplift", "sample_weight_event"
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
            "rolling_30d": Float(),
            "rolling_std_7d": Float(),
            "rolling_std_14d": Float(),
            "rolling_7d_ratio": Float(),
            "trend_7d_ratio": Float(),
            "trend_14d_ratio": Float(),
            "weekend_x_ratas_harian": Float(),
            "payday_x_sisa_pagu": Float(),
            "holiday_x_ratas_harian": Float(),
            "weekend_x_trend": Float(),
            "payday_x_trend": Float(),
            "holiday_x_trend": Float(),
            "lag_1_ratas": Integer(),
            "lag_7_ratas": Integer(),
            "lag_14_ratas": Integer(),
            "lag_7_sisa_pagu": BigInteger(),
            "weekday_sin": Float(),
            "weekday_cos": Float(),
            "payday_x_weekday_sin": Float(),
            "weekend_x_rolling_std_7d": Float(),
            "cum_prev_3d": Float(),
            "cum_prev_7d": Float(),
            "cum_prev_14d": Float(),
            "holiday_count_next_7": Integer(),
            "payday_cluster_flag": SmallInteger(),
            "event_uplift": Float(),
            "sample_weight_event": Float(),
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

    # 4. Visualisasi data
    generate_visualizations(result)

    # 5. Tampilkan ringkasan
    display_summary(result)

    # 6. Simpan ke tabel 'preprocessing' di database
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