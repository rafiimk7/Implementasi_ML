
# Evaluasi Model Prediksi Tanggal Habis ATM

## Model

- Nama model: LightGBM
- Tipe: Regression
- Target: `jumlah_hari`

## Dataset

- Total data: 11,493
- Training: 9,144
- Testing: 2,349
- TID training: 124
- TID testing: 124

## Metode Split

Time-Series Split per TID.

- Training: 80%
- Testing: 20%

Data testing merupakan periode waktu setelah data training pada masing-masing TID.

## Parameter Model

```text
{
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
  "verbosity": -1
}
```

## Hasil Evaluasi

| Metrik | Nilai |
| --- | ---: |
| MAE | 0.1072 hari |
| RMSE | 0.2740 hari |
| R² | 0.9740 |
| Median AE | 0.0035 hari |
| MAPE | 15.14% |
| Error <= 1 hari | 98.85% |
| Error <= 2 hari | 99.70% |
| Error <= 3 hari | 99.96% |

## Baseline Bisnis

| Metrik | Nilai |
| --- | ---: |
| MAE | 0.0132 hari |
| RMSE | 0.1585 hari |
| R² | 0.9913 |

## Perubahan MAE

- Baseline MAE: 0.0132
- Model MAE: 0.1072
- Perubahan: -712.50%

## Status Distribusi

```text
{
  "🔴 Kritis": 2020,
  "🟠 Waspada": 181,
  "🟢 Aman": 148
}
```
