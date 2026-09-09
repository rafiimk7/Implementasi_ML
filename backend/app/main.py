import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.predictions import router as prediction_router
from app.scheduler import create_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ==========================================================
# LIFESPAN — jalankan scheduler saat API start, hentikan saat stop
# ==========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler berjalan.")
    logger.info("API siap menerima request.")

    yield  # aplikasi berjalan di sini

    # Shutdown
    scheduler.shutdown(wait=False)
    logger.info("Scheduler dihentikan.")


# ==========================================================
# APLIKASI
# ==========================================================

app = FastAPI(
    title="Prediksi ATM API",
    version="1.0.0",
    description=(
        "API untuk mengakses hasil prediksi tanggal habis saldo ATM. "
        "Prediksi diperbarui otomatis setiap 15 menit via scheduler incremental. "
        "Model dilatih ulang otomatis setiap minggu."
    ),
    lifespan=lifespan,
)

app.include_router(prediction_router)


@app.get("/")
def root() -> dict:
    return {
        "message": "Prediksi ATM API sedang berjalan",
        "status": "ok",
    }
