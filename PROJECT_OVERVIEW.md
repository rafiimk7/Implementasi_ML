# PROJECT OVERVIEW — Sistem Prediksi ATM

## 1. Informasi Proyek

| Atribut | Detail |
|---|---|
| Nama Proyek | Sistem Prediksi Tanggal Habis Saldo ATM |
| Domain | ATM Cash Management / Operational Monitoring |
| Tujuan | Memprediksi tanggal habis saldo ATM agar refill dapat dilakukan tepat waktu |
| Status | Active development / MVP in progress |
| Stack | FastAPI + Laravel + MySQL + scikit-learn |
| Versi | 1.1.0-dev |

---

## 2. Latar Belakang

Proyek ini dikembangkan untuk membantu operasional ATM dalam memantau kondisi saldo dan memprediksi kapan saldo akan habis. Dengan prediksi yang lebih terukur, tim dapat:

- menyiapkan jadwal refill dengan lebih tepat
- mengurangi risiko ATM kosong saat jam kritis
- memprioritaskan ATM yang masuk kategori kritis
- mengurangi biaya operasional akibat refill yang terlalu cepat atau terlambat

---

## 3. Tujuan Bisnis

1. Optimalisasi refill ATM
2. Meminimalkan risiko downtime layanan
3. Meningkatkan efisiensi operasional
4. Menyediakan dashboard monitoring yang mudah dibaca
5. Mengurangi keputusan berbasis intuisi dan meningkatkan pendekatan data-driven

---

## 4. Arsitektur Sistem

### 4.1 Gambaran Umum

```text
Browser / User
      │
      ▼
Laravel Frontend
  - dashboard summary
  - tabel prediksi per ATM
  - filter dan pencarian
  - status kritis / waspada / aman
      │
      ▼
FastAPI Backend
  - /api/health
  - /api/predictions
  - /api/predictions/{tid}
  - scheduler otomatis
      │
      ▼
MySQL Database
  - data ATM mentah
  - preprocessing
  - hasil_prediksi
  - holiday_cache
      │
      ▼
Python ML Pipeline
  - data_preprocessing.py
  - calendar_features.py
  - train_model.py
  - predict_realtime.py
```

### 4.2 Komponen Utama

- Frontend: Laravel + Blade + Tailwind CSS
- Backend: FastAPI + Python
- Scheduler: APScheduler
- Database: MySQL
- ML: Random Forest Regressor

---

## 5. Fitur yang Sudah Dikembangkan

### 5.1 Preprocessing dan Feature Engineering

Pipeline saat ini sudah mencakup:

- pembacaan data ATM dari database
- aggregasi data harian per TID
- menghitung target business rule
- feature engineering untuk tren, saldo, dan kalender
- validasi target berdasarkan formula bisnis

Target yang dipakai:

```python
jumlah_hari = ceil(sisa_pagu / ratas_harian)
```

### 5.2 Fitur Model

Beberapa fitur utama yang sudah masuk ke pipeline:

- saldo dan penggunaan harian
  - `sisa_pagu`
  - `ratas_harian`
  - `selisih_lmb`
- temporal dasar
  - `hari`, `bulan`, `tahun`, `hari_ke`, `kuartal`
- cyclic encoding
  - `hari_sin`, `hari_cos`
  - `bulan_sin`, `bulan_cos`
  - `hari_ke_sin`, `hari_ke_cos`
- rolling window dan trend
  - `rolling_7d`, `rolling_14d`, `rolling_30d`
  - `rolling_std_7d`, `rolling_std_14d`
  - `trend_7d_ratio`, `trend_14d_ratio`
- kalender cerdas
  - `is_weekend`
  - `is_payday`
  - `is_holiday`
  - `is_near_holiday_3d`
  - `days_to_payday`
  - `days_since_payday`
  - `holiday_count_next_7`
  - `payday_cluster_flag`
- interaction features
  - `weekend_x_ratas_harian`
  - `payday_x_sisa_pagu`
  - `holiday_x_ratas_harian`
  - `weekend_x_trend`
  - `payday_x_trend`
  - `holiday_x_trend`

### 5.3 Calendar Features

File yang menangani kalender cerdas sudah dibuat di:

- `backend/scripts/calendar_features.py`

Fitur kalender yang diterapkan meliputi:

- weekend
- tanggal gajian
- hari libur nasional
- jarak ke libur
- cluster event di sekitar payday/libur

Prioritas datanya:

1. cache database `holiday_cache`
2. Calendarific API bila API key tersedia
3. fallback holiday list bila API gagal

Ini penting agar prediksi tetap stabil walau API libur gagal atau timeout.

---

## 6. Machine Learning Approach

Saat ini pendekatan yang dipakai adalah kombinasi antara business rule dan model machine learning.

### 6.1 Model

- Algoritma: RandomForestRegressor
- Tujuan: memprediksi jumlah hari sampai saldo ATM habis
- Output: `prediksi_hari`, `tanggal_habis`, dan status ATM

### 6.2 Keunggulan Pendekatan Ini

- menangkap pola non-linear dalam transaksi ATM
- lebih adaptif terhadap perubahan pola penggunaan
- memanfaatkan informasi temporal dan kalender untuk meningkatkan interpretasi
- tetap bisa dijelaskan secara bisnis melalui target formula `sisa_pagu / ratas_harian`

---

## 7. Scheduler dan Proses Otomatis

Backend saat ini sudah memiliki scheduler otomatis melalui `app.scheduler`.

Job yang aktif meliputi:

- prediksi realtime untuk memperbarui hasil prediksi secara periodik
- retraining model secara berkala berdasarkan jadwal mingguan

Scheduler diaktifkan saat API startup dan dihentikan saat shutdown aplikasi.

---

## 8. API dan Dashboard

### 8.1 API Backend

FastAPI provides several main endpoints:

- `GET /` — status API
- `GET /api/health` — health check
- `GET /api/predictions` — daftar hasil prediksi
- `GET /api/predictions/{tid}` — detail prediksi per ATM

### 8.2 Dashboard Frontend

Dashboard Laravel menampilkan:

- total ATM
- jumlah ATM kritis, waspada, aman
- rata-rata sisa pagu
- tabel prediksi per TID
- fitur filter dan pencarian

Dashboard ini dipakai untuk visualisasi operasional dan membantu tim mengambil keputusan refill.

---

## 9. Struktur Project Saat Ini

```text
Prediksi_ATM1/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── scheduler.py
│   │   ├── api/routes/predictions.py
│   │   └── services/prediction_service.py
│   ├── config/
│   │   ├── config.py
│   │   └── database.py
│   ├── scripts/
│   │   ├── calendar_features.py
│   │   ├── data_preprocessing.py
│   │   ├── predict_realtime.py
│   │   └── train_model.py
│   ├── tests/
│   ├── models/
│   ├── requirements.txt
│   └── README.md
├── frontend/
│   ├── app/
│   ├── bootstrap/
│   ├── config/
│   ├── public/
│   ├── resources/
│   ├── routes/
│   ├── tests/
│   ├── composer.json
│   ├── package.json
│   └── vite.config.js
├── README.md
├── PROJECT_OVERVIEW.md
└── .gitignore
```

---

## 10. Status Proyek Saat Ini

Proyek saat ini sudah berkembang ke arah sistem yang lebih lengkap dibandingkan tahap awal:

- backend API sudah dibangun
- scheduler otomatis sudah aktif
- dashboard frontend sudah terhubung ke API
- preprocessing dan feature engineering sudah lebih kompleks
- kalender cerdas sudah ditambahkan
- fallback holiday management sudah ada sebagai pengaman

Yang masih menjadi fokus pengembangan lanjutan:

- validasi akurasi model terhadap data aktual lapangan
- tuning parameter model
- penguatan fitur event dan kalender
- stabilisasi deployment production
- monitoring dan observability untuk operasional nyata

---

## 11. Kesimpulan

Proyek ini sudah masuk ke fase pengembangan fungsional yang cukup matang: pipeline data, model prediksi, scheduler, API, dan dashboard telah dibangun dalam satu sistem terpadu. Fokus saat ini bukan lagi sekadar membuat prototipe, melainkan meningkatkan kualitas prediksi, keandalan pipeline, dan kesiapan sistem untuk kebutuhan operasional yang lebih nyata di lapangan.
