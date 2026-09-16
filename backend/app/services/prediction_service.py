import pandas as pd

from config.config import get_db_engine

PREDICTION_TABLE = "hasil_prediksi"

# Kolom datetime yang perlu dikonversi ke string agar JSON-serializable
_DATETIME_COLS = ["updated", "prediksi_at"]
_DATETIME_FMT  = "%Y-%m-%d %H:%M:%S"


def _serialize_row(row: dict) -> dict:
    """Konversi Timestamp, NaT, NaN dan tipe non-serializable ke tipe Python native."""
    import math
    result = {}
    for k, v in row.items():
        # NaT (Not a Time) — pandas sentinel untuk datetime kosong
        if v is pd.NaT:
            result[k] = None
        elif isinstance(v, pd.Timestamp):
            result[k] = v.strftime(_DATETIME_FMT) if not pd.isnull(v) else None
        elif hasattr(v, "item"):
            # numpy int/float → Python native
            native = v.item()
            # float NaN → None
            result[k] = None if isinstance(native, float) and math.isnan(native) else native
        elif isinstance(v, float) and math.isnan(v):
            result[k] = None
        else:
            result[k] = v
    return result


def load_predictions() -> list[dict]:
    """Membaca seluruh hasil prediksi dari tabel MySQL."""
    try:
        engine = get_db_engine()
        df = pd.read_sql(f"SELECT * FROM {PREDICTION_TABLE}", con=engine)
        return [_serialize_row(row) for row in df.to_dict(orient="records")]
    except Exception as exc:
        raise FileNotFoundError(
            f"Tabel '{PREDICTION_TABLE}' tidak ditemukan atau belum dibuat. "
            "Jalankan predict_realtime.py atau train_model.py terlebih dahulu."
        ) from exc


def get_prediction_by_tid(tid: str) -> dict | None:
    """Mengambil satu record prediksi berdasarkan TID."""
    try:
        engine = get_db_engine()
        df = pd.read_sql(
            f"SELECT * FROM {PREDICTION_TABLE} WHERE tid = %(tid)s",
            con=engine,
            params={"tid": tid},
        )
        if df.empty:
            return None
        return _serialize_row(df.iloc[0].to_dict())
    except Exception as exc:
        raise FileNotFoundError(
            f"Tabel '{PREDICTION_TABLE}' tidak ditemukan atau belum dibuat. "
            "Jalankan predict_realtime.py atau train_model.py terlebih dahulu."
        ) from exc
