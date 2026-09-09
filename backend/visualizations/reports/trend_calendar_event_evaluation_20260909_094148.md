# Evaluasi Model Trend & Kalender ATM

- Tanggal: 2026-09-09 09:41:48
- Tipe model: calendar_trend_model
- Data train: 2630 baris
- Data test: 697 baris
- TID uji: 74

## Fokus fitur

- is_weekend
- is_payday
- is_holiday
- days_to_payday
- days_since_payday
- is_near_holiday_3d
- trend_7d_ratio
- rolling_7d_ratio
- weekend_x_trend
- payday_x_trend
- holiday_x_trend

## Pola tren yang dipertimbangkan

- Weekend: weekend effect on demand and withdrawal pattern
- Tanggal merah: holiday impact on ATM usage and liquidity pressure
- Gajian: payday effect on withdrawal intensity and cash depletion

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
