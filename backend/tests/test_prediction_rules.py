import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.predict_realtime import (
    apply_business_rule_fallback,
    assign_threshold,
    business_rule_days,
    normalize_prediction_days,
    status_from_hari,
)


def test_business_rule_days_zero_when_remaining_balance_below_daily_average():
    assert business_rule_days(748, 2989) == 0


def test_business_rule_days_casts_to_int_before_subtracting_one():
    assert business_rule_days(250, 100) == 1
    assert business_rule_days(3952, 1376) == 1


def test_apply_business_rule_fallback_keeps_full_model_predictions_when_disabled():
    df = pd.DataFrame([
        {"tid": "A", "updated": "2026-01-01", "sisa_pagu": 50, "ratas_harian": 100, "prediksi_hari": 9},
        {"tid": "B", "updated": "2026-01-02", "sisa_pagu": 250, "ratas_harian": 100, "prediksi_hari": 1},
    ])

    result = apply_business_rule_fallback(df)

    assert result["prediksi_hari"].tolist() == [9, 1]


def test_normalize_prediction_days_reduces_model_output_by_one_before_storage():
    df = pd.DataFrame({"prediksi_hari": [5, 1, 0]})

    result = normalize_prediction_days(df)

    assert result["prediksi_hari"].tolist() == [4, 0, 0]


def test_assign_threshold_uses_three_status_levels():
    df = pd.DataFrame({"prediksi_hari": [0, 1, 2, 3, 4]})

    result = assign_threshold(df)

    assert result["threshold"].tolist() == [
        "🔴 Kritis",
        "🔴 Kritis",
        "🟠 Waspada",
        "🟠 Waspada",
        "🟢 Aman",
    ]


def test_status_from_hari_has_single_source_of_truth():
    assert status_from_hari(0) == "🔴 Kritis"
    assert status_from_hari(1) == "🔴 Kritis"
    assert status_from_hari(2) == "🟠 Waspada"
    assert status_from_hari(3) == "🟠 Waspada"
    assert status_from_hari(4) == "🟢 Aman"
    assert status_from_hari(None) == "🟢 Aman"
