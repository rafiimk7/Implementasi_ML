"""
Scheduler Otomatis
------------------
Menjalankan dua job berkala:

  1. [PREDIKSI] Preprocessing + prediksi realtime setiap N menit.
     Cek data RAW baru via checkpoint, skip jika tidak ada perubahan.
     UPSERT hanya TID terdampak ke hasil_prediksi.

  2. [RETRAINING] Full preprocessing + training model setiap Minggu 02.00 WIB.
     Setelah selesai, refresh hasil_prediksi dan reset checkpoint.

Konfigurasi via environment variables:
  PREDICT_INTERVAL_MINUTES (default: 15)
  PREDICT_WINDOW_DAYS      (default: 31) — tidak dipakai di pipeline ini
  RETRAIN_DAY_OF_WEEK      (default: sun)
  RETRAIN_HOUR             (default: 2)

Catatan:
  - Variabel lama PREDICT_INTERVAL_HOURS masih didukung untuk kompatibilitas.
  - Setelah retraining, checkpoint di-reset agar semua TID diproses ulang.
"""

import logging
import os
import sys
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# Pastikan root project ada di sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# ----------------------------------------------------------
# KONFIGURASI (bisa di-override via env)
# ----------------------------------------------------------
# Prioritas konfigurasi:
# 1. PREDICT_INTERVAL_MINUTES (mode baru)
# 2. PREDICT_INTERVAL_HOURS (legacy compatibility, dikonversi ke menit)
# 3. fallback default 15 menit
PREDICT_INTERVAL_MINUTES = int(
    os.getenv("PREDICT_INTERVAL_MINUTES")
    or (int(os.getenv("PREDICT_INTERVAL_HOURS", 0)) * 60 if os.getenv("PREDICT_INTERVAL_HOURS") else 15)
)
PREDICT_WINDOW_DAYS     = int(os.getenv("PREDICT_WINDOW_DAYS", "31"))
RETRAIN_DAY_OF_WEEK     = os.getenv("RETRAIN_DAY_OF_WEEK", "sun")
RETRAIN_HOUR            = int(os.getenv("RETRAIN_HOUR", 2))


# ==========================================================
# JOB 1 — PREDIKSI REALTIME INCREMENTAL (setiap N menit)
# ==========================================================

def job_predict_realtime() -> None:
    """
    Job siklus pendek (default 15 menit).

    Alur:
      1. Cek apakah ada data RAW baru sejak checkpoint terakhir.
      2. Jika tidak ada → SKIP.
      3. Jika ada:
           - Jalankan preprocessing (full rebuild preprocessing).
           - Baca 1 baris terbaru per TID dari preprocessing.
           - Filter TID terdampak → model.predict().
           - UPSERT ke hasil_prediksi.
           - Simpan checkpoint.

    Tidak melakukan training ulang.
    """
    logger.info("[Scheduler] ── Memulai siklus prediksi realtime ──")
    scripts_path = PROJECT_ROOT / "scripts"
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))

    try:
        from data_preprocessing import main as preprocess_main
        from predict_realtime   import main as predict_main

        logger.info("[Scheduler] Tahap 1/2: preprocessing raw data...")
        preprocess_main()

        logger.info("[Scheduler] Tahap 2/2: prediksi realtime...")
        predict_main()

        logger.info("[Scheduler] Siklus prediksi selesai — hasil_prediksi diperbarui.")

    except Exception as e:
        logger.error(f"[Scheduler] Prediksi realtime gagal: {e}", exc_info=True)


# ==========================================================
# JOB 2 — PREPROCESSING + RETRAINING (setiap Minggu jam 02.00)
# ==========================================================

def job_retrain() -> None:
    """
    Job mingguan — FULL preprocessing + retraining.

    Alur:
      1. Baca seluruh data historis → rebuild preprocessing (full replace).
      2. Training ulang model dengan data terbaru.
      3. Jalankan predict_realtime (full) sekali untuk refresh hasil_prediksi
         dengan model baru.
      4. Reset checkpoint incremental agar siklus berikutnya memproses
         semua TID dengan model yang baru dilatih.
    """
    logger.info("[Scheduler] ── Memulai retraining model (full pipeline) ──")

    scripts_path = PROJECT_ROOT / "scripts"
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))

    try:
        from data_preprocessing import main as preprocess_main
        from train_model        import main as train_main
        from predict_realtime   import main as predict_main

        logger.info("[Scheduler] Tahap 1/3: Full preprocessing...")
        preprocess_main()

        logger.info("[Scheduler] Tahap 2/3: Training model...")
        train_main()

        logger.info("[Scheduler] Tahap 3/3: Full prediction (refresh hasil_prediksi)...")
        predict_main()

        # Reset checkpoint agar incremental pertama setelah retrain
        # memproses ulang semua TID dengan model baru
        _reset_checkpoint()

        logger.info("[Scheduler] Retraining selesai. Model dan hasil_prediksi diperbarui.")
    except Exception as e:
        logger.error(f"[Scheduler] Retraining gagal: {e}", exc_info=True)


def _reset_checkpoint() -> None:
    """
    Hapus checkpoint incremental agar run berikutnya
    memproses semua TID (diperlukan setelah model baru dilatih).
    """
    from pathlib import Path
    checkpoint_path = PROJECT_ROOT / "models" / "checkpoint.json"
    if checkpoint_path.exists():
        try:
            checkpoint_path.unlink()
            logger.info("[Scheduler] Checkpoint incremental di-reset (model baru aktif).")
        except OSError as e:
            logger.warning(f"[Scheduler] Gagal reset checkpoint: {e}")


# ==========================================================
# SETUP SCHEDULER
# ==========================================================

def create_scheduler() -> BackgroundScheduler:
    """Membuat dan mendaftarkan job ke scheduler."""
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")

    # Job 1: Prediksi realtime setiap N menit
    scheduler.add_job(
        func=job_predict_realtime,
        trigger=IntervalTrigger(minutes=PREDICT_INTERVAL_MINUTES),
        id="predict_realtime",
        name="Prediksi Realtime ATM",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )

    # Job 2: Retraining setiap Minggu jam 00.00 WIB
    scheduler.add_job(
        func=job_retrain,
        trigger=CronTrigger(
            day_of_week=RETRAIN_DAY_OF_WEEK,
            hour=RETRAIN_HOUR,
            minute=0,
        ),
        id="retrain_model",
        name="Retraining Model ATM",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600, 
    )

    logger.info(
        f"[Scheduler] Job terdaftar:\n"
        f"  - Prediksi realtime : setiap {PREDICT_INTERVAL_MINUTES} menit\n"
        f"  - Retraining model  : setiap {RETRAIN_DAY_OF_WEEK} jam {RETRAIN_HOUR:02d}:00 WIB"
    )

    return scheduler
