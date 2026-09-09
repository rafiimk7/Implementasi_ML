# Evaluasi Model Gabungan Rule-Based + Trend ATM

- Tanggal: 2026-09-09 09:44:10
- Tipe model: hybrid_rule_and_trend_model
- Data train: 2630 baris
- Data test: 697 baris
- TID uji: 74

## Kombinasi 

- berbasis aturan: status berdasarkan sisa saldo dan tingkat penarikan harian
- berbasis tren: kalender dan perilaku tren yang dipengaruhi oleh akhir pekan, hari libur, dan waktu penerimaan gaji
- Logika gabungan: aturan dan tren digabungkan dalam satu set fitur untuk prediksi akhir
## Fokus fitur utama

- sisa_pagu
- ratas_harian
- trend_7d_ratio
- rolling_7d_ratio
- is_weekend
- is_payday
- is_holiday
- days_to_payday
- days_since_payday
- weekend_x_trend
- payday_x_trend
- holiday_x_trend

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
