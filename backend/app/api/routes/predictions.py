import logging

from fastapi import APIRouter, HTTPException

from app.services.prediction_service import get_prediction_by_tid, load_predictions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["prediction"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/predictions")
def list_predictions() -> dict:
    try:
        data = load_predictions()
        return {
            "count": len(data),
            "data": data,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/predictions/{tid}")
def prediction_by_tid(tid: str) -> dict:
    try:
        result = get_prediction_by_tid(tid)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Prediksi untuk TID {tid} tidak ditemukan",
        )

    return result
