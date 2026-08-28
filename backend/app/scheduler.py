"""
Scheduler Otomatis
------------------
Menjalankan dua job berkala:
  1. Prediksi realtime → setiap {PREDICT_INTERVAL_HOURS} jam (mengupdate tabel hasil_prediksi)
  2. Preprocessing + retraining model → setiap Minggu jam 02.00 WIB

Konfigurasi via environment variables:
  PREDICT_INTERVAL_HOURS  (default: 6)
  RETRAIN_DAY_OF_WEEK       (default: sun)
  RETRAIN_HOUR              (default: 2)
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
PREDICT_INTERVAL_HOURS = int(os.getenv("PREDICT_INTERVAL_HOURS", 6))
RETRAIN_DAY_OF_WEEK      = os.getenv("RETRAIN_DAY_OF_WEEK", "sun")
RETRAIN_HOUR             = int(os.getenv("RETRAIN_HOUR", 2))


# ==========================================================
# JOB — PREDIKSI REALTIME 
# ==========================================================

def job_predict_realtime() -> None:
    """
    Menjalankan predict_realtime.py untuk mengupdate tabel hasil_prediksi
    dengan data terbaru per TID. Job ini berjalan setiap {PREDICT_INTERVAL_HOURS} jam.
    """
    logger.info("[Scheduler] Memulai prediksi realtime...")
    7
    # Pastikan scripts/ ada di sys.path
    scripts_path = PROJECT_ROOT / "scripts"
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))
    
    try:
        from predict_realtime import main as predict_main
        
        predict_main()
        logger.info("[Scheduler] Prediksi realtime selesai. Tabel hasil_prediksi diperbarui.")
    except Exception as e:
        logger.error(f"[Scheduler] Prediksi realtime gagal: {e}", exc_info=True)


# ==========================================================
# JOB — PREPROCESSING + RETRAINING (setiap Minggu jam 02.00)
# ==========================================================

def job_retrain() -> None:
    """
    Menjalankan ulang preprocessing dan training model
    berdasarkan seluruh data terbaru di database.
    """
    logger.info("[Scheduler] Memulai retraining model...")
    
    # Pastikan scripts/ ada di sys.path
    scripts_path = PROJECT_ROOT / "scripts"
    if str(scripts_path) not in sys.path:
        sys.path.insert(0, str(scripts_path))
    
    try:
        from data_preprocessing import main as preprocess_main
        from train_model import main as train_main

        logger.info("[Scheduler] Tahap 1/2: Preprocessing...")
        preprocess_main()

        logger.info("[Scheduler] Tahap 2/2: Training model...")
        train_main()

        logger.info("[Scheduler] Retraining selesai. Model diperbarui.")
    except Exception as e:
        logger.error(f"[Scheduler] Retraining gagal: {e}", exc_info=True)


# ==========================================================
# SETUP SCHEDULER
# ==========================================================

def create_scheduler() -> BackgroundScheduler:
    """Membuat dan mendaftarkan job ke scheduler."""
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")

    # Job 1: Prediksi realtime setiap N jam 
    scheduler.add_job(
        func=job_predict_realtime,
        trigger=IntervalTrigger(hours=PREDICT_INTERVAL_HOURS),
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
        f"  - Prediksi realtime : setiap {PREDICT_INTERVAL_HOURS} jam\n"
        f"  - Retraining model  : setiap {RETRAIN_DAY_OF_WEEK} jam {RETRAIN_HOUR:00d}:00 WIB"
    )

    return scheduler
