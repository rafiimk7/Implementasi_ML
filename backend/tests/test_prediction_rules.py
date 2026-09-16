import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.predict_realtime import (
    apply_business_rule_fallback,
    assign_threshold,
    business_rule_days,
    status_from_hari,
)


def test_business_rule_days_zero_when_remaining_balance_below_daily_average():
    assert business_rule_days(748, 2989) == 0


def test_business_rule_days_casts_to_int_before_subtracting_one():
    assert business_rule_days(250, 100) == 1
    assert business_rule_days(3952, 1376) == 1


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


def test_apply_business_rule_fallback_keeps_model_prediction_without_override():
    df = pd.DataFrame(
        {
            "prediksi_hari": [10],
            "sisa_pagu": [5000],
            "ratas_harian": [1000],
            "updated": [pd.Timestamp("2026-09-10")],
        }
    )

    result = apply_business_rule_fallback(df)

    assert result["prediksi_hari"].iloc[0] == 10
    assert result["threshold"].iloc[0] == "🟢 Aman"


def test_apply_business_rule_fallback_keeps_model_if_rule_differs_significantly():
    df = pd.DataFrame(
        {
            "prediksi_hari": [3],
            "sisa_pagu": [4000],
            "ratas_harian": [1000],
            "updated": [pd.Timestamp("2026-09-10")],
        }
    )

    result = apply_business_rule_fallback(df)

    assert result["prediksi_hari"].iloc[0] == 3
    assert result["threshold"].iloc[0] == "🟠 Waspada"
