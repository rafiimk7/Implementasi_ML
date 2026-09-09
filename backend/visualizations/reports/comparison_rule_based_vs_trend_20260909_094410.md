# Perbandingan Model: Rule-Based vs Trend

Tanggal: 2026-09-09 09:44:10

## Ringkasan

Dari hasil evaluasi yang tersimpan, model rule-based dan model trend/calendar memiliki performa yang sama pada dataset dan split saat ini.

## Tabel Perbandingan

| Model | MAE (hari) | R² | MAPE (%) |
|---|---:|---:|---:|
| Rule-based baseline | 0.2154 | 0.9727 | 9.20 |
| Trend/calendar | 0.2154 | 0.9727 | 9.20 |

## Distribusi status

### Rule-based baseline
```json
{
  "🔴 Kritis": 390,
  "🟠 Waspada": 161,
  "🟢 Aman": 146
}
```

### Trend/calendar
```json
{
  "🔴 Kritis": 390,
  "🟠 Waspada": 161,
  "🟢 Aman": 146
}
```

## Kesimpulan

Kedua model tidak menunjukkan peningkatan signifikan terhadap baseline. Dengan demikian, rule-based tetap dipilih sebagai baseline utama karena lebih sederhana, konsisten, dan lebih mudah dijelaskan secara bisnis. Fitur weekend, tanggal merah, dan gajian dapat dipertahankan sebagai variabel pendukung, tetapi belum terbukti meningkatkan akurasi pada konfigurasi saat ini.
