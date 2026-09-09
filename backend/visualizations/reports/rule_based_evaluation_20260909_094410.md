# Evaluasi Baseline Rule-Based ATM

- Tanggal: 2026-09-09 09:44:10
- Tipe model: rule_based_baseline
- Data train: 2630 baris
- Data test: 697 baris
- TID uji: 74

## Aturan status

- Kritis: <= 1 hari
- Waspada: 2 sampai 3 hari
- Aman: > 3 hari

## Metrik evaluasi

- MAE: 0.22 hari
- R²: 0.9727
- MAPE: 9.20%

## Distribusi status hasil prediksi

```json
{
  "🔴 Kritis": 390,
  "🟠 Waspada": 161,
  "🟢 Aman": 146
}
```
