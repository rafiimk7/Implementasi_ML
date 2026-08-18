# Sistem Prediksi Tanggal Habis Saldo ATM

Aplikasi full-stack untuk memprediksi tanggal habis saldo ATM menggunakan machine learning (Random Forest) berbasis business rule. Terdiri dari **backend FastAPI** (Python) untuk ML pipeline & REST API, dan **frontend Laravel** (PHP) untuk dashboard monitoring.

---

## 📌 Quick Overview

| Komponen | Teknologi | Port | Deskripsi |
|---|---|---|---|
| **Backend** | FastAPI + scikit-learn | 8001 | ML pipeline, prediksi otomatis, REST API |
| **Frontend** | Laravel 13 + Tailwind CSS | 8000 | Dashboard web monitoring |
| **Database** | MySQL 5.7+ | 3306 | Data ATM, hasil preprocessing, prediksi |

**ML Approach**: Business rule-based — target training (`jumlah_hari`) dihitung dari formula `ceil(sisa_pagu / ratas_harian)`, bukan ground truth refill events. Model diperkaya dengan **fitur kalender cerdas** (hari gajian, akhir pekan, libur nasional) untuk menangkap pola penarikan tunai pada event-event spesial.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.9+
- PHP 8.3+
- MySQL 5.7+
- Composer
- Node.js 16+ & npm

### 1. Clone Repository

```bash
cd Prediksi_ATM1/
```

### 2. Setup Backend

```bash
cd backend/
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure database
export DB_HOST=localhost
export DB_USER=root
export DB_PASSWORD=your_password
export DB_NAME=PT_BGI

# Run ML pipeline
python3 scripts/data_preprocessing.py
python3 scripts/train_model.py

# Start API
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Backend API tersedia di `http://127.0.0.1:8001/docs`


### 3. Setup Frontend

```bash
cd ../frontend/
composer install
cp .env.example .env
php artisan key:generate
touch database/database.sqlite
php artisan migrate

npm install
npm run build

# Start Laravel server
php artisan serve
```

Frontend tersedia di `http://127.0.0.1:8000`

---

## 📐 Arsitektur Sistem

```
┌──────────────────────────────────────────────────────────────────┐
│                        Browser (User)                             │
│                   http://127.0.0.1:8000                           │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FRONTEND (Laravel 13)                          │
│                                                                   │
│  Routes:  GET /  → DashboardController@index                      │
│                                                                   │
│  Service: ApiService (HTTP Client ke Backend)                     │
│  View:    dashboard.blade.php (Tailwind CSS)                      │
│           ├── Summary Cards (Total/Kritis/Waspada/Aman)          │
│           ├── Search & Filter by Status                           │
│           └── Sortable Table                                      │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP (Guzzle)
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI + Python)                    │
│                   http://127.0.0.1:8001/api                      │
│                                                                  │
│  API Endpoints:                                                  │
│    GET  /api/predictions      → List semua prediksi              │
│    GET  /api/predictions/{tid} → Prediksi per TID                │
│    GET  /api/health            → Health check                    │
│                                                                  │
│  Scheduler (APScheduler):                                        │
│    ⏰ Prediksi realtime: setiap 6 jam                            │
│    ⏰ Retraining model: setiap Minggu 02.00 WIB                  │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                         MySQL Database                           │
│                                                                  │
│  Tabel:                                                          │
│    ├── Data_mei2026      → Data mentah ATM (source)              │
│    ├── preprocessing     → Hasil ETL + feature engineering       │
│    └── hasil_prediksi    → Output prediksi terbaru (API source)  │
└──────────────────────────────────────────────────────────────────┘
```

---


## 🧠 Machine Learning Approach

### ⚠️ Business Rule-Based ML

**Target training bukan ground truth**, melainkan hasil kalkulasi business rule:

```
jumlah_hari = ceil(sisa_pagu / ratas_harian)
```

**Mengapa tetap pakai ML?**
1. Model belajar pola temporal (akhir bulan → pemakaian meningkat)
2. Menangkap interaksi fitur non-linear
3. Generalisasi untuk ATM baru tanpa historis


### Model Details

| Atribut | Detail |
|---|---|
| Algoritma | RandomForestRegressor (scikit-learn) |
| Estimators | 100 pohon, max_depth=8 |
| Features | **17 fitur** (balance, pemakaian, kalender, cyclic encoding, kalender cerdas) |
| Target | `jumlah_hari` (dari rumus business rule) |
| Preprocessing | StandardScaler |
| Split | 80% train / 20% test (random) |
| Metrics | MAE ±2.8 hari, R² ±0.78 |

### Fitur ML (17 fitur)

| Kategori | Fitur | Keterangan |
|---|---|---|
| **Balance & Usage** | `sisa_pagu` | Saldo tersisa (pagu - total_lmb) |
| | `ratas_harian` | Rata-rata penarikan harian per TID |
| | `selisih_lmb` | Selisih penarikan dari transaksi terakhir |
| **Kalender Dasar** | `hari`, `bulan`, `tahun` | Tanggal transaksi |
| | `hari_ke` | Hari ke-N dalam tahun (1-366) |
| | `kuartal` | Kuartal (1-4) |
| **Cyclic Encoding** | `hari_sin`, `hari_cos` | Encoding siklik hari dalam bulan |
| | `bulan_sin`, `bulan_cos` | Encoding siklik bulan dalam tahun |
| | `hari_ke_sin`, `hari_ke_cos` | Encoding siklik hari dalam tahun |
| **Kalender Cerdas** | `is_weekend` | 1 jika Sabtu/Minggu, else 0 |
| | `is_payday` | 1 jika hari gajian bulan itu, else 0 |
| | `is_holiday` | 1 jika libur nasional Indonesia, else 0 |

**Cyclic encoding** menangkap periodisitas waktu: akhir bulan dekat dengan awal bulan (31 ≈ 1), Desember dekat dengan Januari (12 ≈ 1).

**Kalender cerdas** menangkap pola penarikan pada event spesial: ATM cenderung lebih cepat kosong di hari gajian, sebelum/sesudah libur panjang, dan di akhir pekan.

---


## 📂 Struktur Project

```
Prediksi_ATM1/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI entry point + scheduler
│   │   ├── scheduler.py               # APScheduler config
│   │   ├── api/routes/
│   │   │   └── predictions.py         # API endpoints
│   │   └── services/
│   │       └── prediction_service.py  # Load data dari DB
│   ├── config/
│   │   ├── config.py                  # Database connection + calendar config
│   │   └── database.py                # SQLAlchemy session
│   ├── models/
│   │   ├── model_prediksi_habis.pkl   # Trained Random Forest
│   │   ├── scaler.pkl                 # StandardScaler
│   │   └── fitur.pkl                  # Feature list
│   ├── scripts/
│   │   ├── calendar_features.py       # Fitur kalender cerdas (payday/weekend/holiday)
│   │   ├── data_preprocessing.py      # ETL + feature engineering
│   │   ├── train_model.py             # Training ML model
│   │   └── predict_realtime.py        # Inference on latest data
│   ├── tests/
│   │   └── test_calendar_features.py  # Unit tests kalender cerdas
│   ├── .env.example                   # Template environment variables
│   └── requirements.txt               # Python dependencies
│
├── frontend/
│   ├── app/
│   │   ├── Http/Controllers/
│   │   │   └── DashboardController.php
│   │   └── Services/
│   │       └── ApiService.php         # HTTP client ke backend
│   ├── resources/
│   │   ├── css/app.css                # Tailwind CSS
│   │   └── views/
│   │       └── dashboard.blade.php    # Dashboard UI
│   ├── routes/web.php                 # Routes Laravel
│   ├── composer.json                  # PHP dependencies
│   └── package.json                   # npm dependencies
│
└── README.md
```

---

## 🔧 Backend Details

### Tech Stack

| Layer | Teknologi | Versi |
|---|---|---|
| Framework | FastAPI | 0.141.1 |
| Server | Uvicorn | 0.52.1 |
| ML | scikit-learn | 1.7.2 |
| Data | pandas | 2.3.3, NumPy | 2.2.6 |
| Database | SQLAlchemy + PyMySQL | 2.0.51 + 2.2.8 |
| Scheduler | APScheduler | 3.11.3 |

### Tabel Database

#### `data_2026` (Source)
Data mentah ATM historis/realtime.

| Kolom | Tipe | Keterangan |
|---|---|---|
| tid | VARCHAR | ID terminal ATM |
| updated | DATETIME | Timestamp data |
| lmb1-lmb4 | BIGINT | Saldo per kaset |
| pagu_existing | BIGINT | Kapasitas maksimal ATM |

#### `preprocessing` (ETL Result)
Hasil preprocessing + feature engineering, digunakan untuk training.

| Kolom | Tipe | Keterangan |
|---|---|---|
| tid | VARCHAR(50) | ID terminal |
| tanggal | DATE | Tanggal agregasi harian |
| updated | DATETIME | Timestamp terakhir |
| total_lmb | BIGINT | Total saldo seluruh kaset |
| sisa_pagu | BIGINT | Saldo tersisa |
| ratas_harian | INT | Rata-rata pemakaian harian |
| jumlah_hari | INT | Target ML (business rule) |
| tanggal_habis | VARCHAR(20) | Estimasi tanggal habis |
| hari, bulan, tahun, hari_ke, kuartal | SMALLINT | Fitur kalender |
| *_sin, *_cos | FLOAT | Cyclic encoding |
| is_weekend | SMALLINT | 1 jika Sabtu/Minggu, else 0 |
| is_payday | SMALLINT | 1 jika hari gajian, else 0 |
| is_holiday | SMALLINT | 1 jika libur nasional, else 0 |

#### `holiday_cache` (Calendar API Cache)
Cache data libur nasional dari Calendarific API, dibuat otomatis saat pertama kali API dipanggil.

| Kolom | Tipe | Keterangan |
|---|---|---|
| id | INT | Auto increment PK |
| tanggal | DATE | Tanggal libur |
| nama | VARCHAR(150) | Nama hari libur |
| tahun | SMALLINT | Tahun (untuk query efisien) |

#### `hasil_prediksi` (Prediction Output)
Output prediksi terbaru per TID, diakses oleh API.

| Kolom | Tipe | Keterangan |
|---|---|---|
| tid | VARCHAR(50) | ID terminal |
| updated | DATETIME | Timestamp data terakhir |
| sisa_pagu | BIGINT | Saldo tersisa |
| ratas_harian | INT | Rata-rata pemakaian |
| prediksi_hari | INT | Hasil prediksi (hari) |
| tanggal_habis | VARCHAR(20) | Tanggal estimasi habis |
| prediksi_at | DATETIME | Timestamp prediksi dibuat |


### ML Pipeline

**1. Preprocessing** (`scripts/data_preprocessing.py`)

```
data_2026 → Load → Konversi dtype → Hitung total_lmb
    ↓
Agregasi harian per TID → Hitung selisih_lmb (diff per TID)
    ↓
Hitung ratas_harian per TID → Hitung sisa_pagu
    ↓
Hitung jumlah_hari (business rule: sisa_pagu / ratas_harian)
    ↓
Feature engineering: hari, bulan, tahun, hari_ke, kuartal, cyclic encoding
    ↓
Calendar flags: is_weekend, is_payday, is_holiday (via calendar_features.py)
    ↓
Simpan ke tabel preprocessing (dengan dtype mapping SQLAlchemy)
```

**2. Training** (`scripts/train_model.py`)

```
Load tabel preprocessing → Filter valid data (jumlah_hari > 0)
    ↓
Train-test split (80/20, random_state=42)
    ↓
StandardScaler → RandomForestRegressor (100 trees, max_depth=8)
    ↓
Evaluate: MAE, R² → Prediksi data terbaru per TID
    ↓
Simpan model (pkl) + hasil prediksi ke tabel hasil_prediksi
```

**3. Real-time Prediction** (`scripts/predict_realtime.py`)

```
Load data terbaru per TID (MAX(updated)) dari Data_mei2026
    ↓
Load ratas_harian historis dari tabel preprocessing
    ↓
Preprocessing ringan + feature engineering
    ↓
Load trained model → Predict → Hitung tanggal_habis
    ↓
Simpan ke tabel hasil_prediksi (replace)
```

### Scheduler Otomatis

Saat API berjalan (`app.main:app`), APScheduler otomatis menjalankan:

| Job | Jadwal | Script |
|---|---|---|
| **Prediksi Realtime** | Setiap 15 menit | `predict_realtime.py` |
| **Retraining Model** | Setiap Minggu, 02.00 WIB | `data_preprocessing.py` + `train_model.py` |

### API Endpoints

Base URL: `http://127.0.0.1:8001`

| Method | Endpoint | Response |
|---|---|---|
| GET | `/` | `{ "message": "...", "status": "ok" }` |
| GET | `/api/health` | `{ "status": "ok" }` |
| GET | `/api/predictions` | `{ "count": N, "data": [...] }` |
| GET | `/api/predictions/{tid}` | `{ "tid": "...", "prediksi_hari": N, ... }` |

**Dokumentasi interaktif:** `http://127.0.0.1:8001/docs`

---


## 🎨 Frontend Details

### Tech Stack

| Layer | Teknologi | Versi |
|---|---|---|
| Framework | Laravel | 13.8 |
| Language | PHP | 8.3 |
| Template | Blade | built-in |
| CSS | Tailwind CSS | 4.0 |
| Build Tool | Vite | 8.0 |
| HTTP Client | Guzzle | built-in (via `Http` facade) |
| Session/Cache | SQLite | built-in |

### Fitur Dashboard

**1. Summary Cards**
- Total ATM
- Kritis (≤3 hari) — merah
- Waspada (4-7 hari) — kuning
- Aman (>7 hari) — hijau

**2. Tabel Prediksi**
- Kolom: #, TID, Sisa Pagu, Rata Harian, Prediksi Hari, Tanggal Habis, Status, Update Prediksi
- Search by TID (real-time filter)
- Filter by Status (dropdown)
- Sort kolom (klik header)

**3. Responsive Design**
- Mobile-friendly (2 kolom cards, horizontal scroll tabel)
- Tailwind CSS utility classes
- Empty state jika backend tidak tersedia

### Routes

| Method | URI | Controller | Keterangan |
|---|---|---|---|
| GET | `/` | DashboardController@index | Dashboard utama |

### Flow

```
Browser → GET / → DashboardController@index()
    ↓
ApiService->getPredictions()
    ↓
Backend: GET /api/predictions
    ↓
Response: { "count": N, "data": [...] }
    ↓
Render dashboard.blade.php
    ├── Hitung summary (kritis/waspada/aman)
    ├── Loop tabel dari $prediction['data']
    └── JS client-side (search, filter, sort)
```

---


## ⚙️ Konfigurasi

### Backend `.env` (atau export)

```bash
# Database
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=PT_BGI

# Tabel sumber data ATM
SOURCE_TABLE=data_mei2026

# Fitur kalender cerdas
PAYDAY_DATE=25                          # "25" atau "last_workday"
CALENDARIFIC_API_KEY=your_api_key_here  # dari https://calendarific.com
HOLIDAY_COUNTRY=ID                      # kode negara ISO-3166

# Scheduler config (optional)
RETRAIN_DAY_OF_WEEK=sun  # mon/tue/wed/thu/fri/sat/sun
RETRAIN_HOUR=2           # Jam retraining (24-hour format)
PREDICT_INTERVAL_MINUTES=5
```

Salin template dari `backend/.env.example`:

```bash
cp backend/.env.example backend/.env
# Edit .env sesuai environment kamu
```

### Frontend `.env`

```env
APP_NAME=Laravel
APP_ENV=local
APP_DEBUG=true
APP_URL=http://localhost

DB_CONNECTION=sqlite
```

**Backend API URL** di-set di `frontend/app/Services/ApiService.php`:

```php
protected $baseUrl = 'http://127.0.0.1:8001';
```

---

## 🛠️ Maintenance & Troubleshooting

### Menjalankan Script Manual

#### Backend

```bash
cd backend/
source .venv/bin/activate

# Preprocessing + feature engineering
python3 scripts/data_preprocessing.py

# Training model
python3 scripts/train_model.py

# Prediksi realtime
python3 scripts/predict_realtime.py
```

#### Frontend

```bash
cd frontend/

# Development mode (hot reload)
npm run dev

# Production build
npm run build
```

### Common Issues

**1. Frontend tidak bisa akses backend**

**Error:** `Failed to fetch: http://127.0.0.1:8001/api/predictions`

**Solusi:**
- Pastikan backend berjalan: `uvicorn app.main:app --host 127.0.0.1 --port 8001`
- Cek URL di `frontend/app/Services/ApiService.php`

**3. MySQL Connection Error**

**Error:** `Can't connect to MySQL server`

**Solusi:**
- Cek MySQL service: `sudo systemctl status mysql`
- Verifikasi credentials di backend `.env` atau export

**4. Model tidak ditemukan**

**Error:** `FileNotFoundError: models/model_prediksi_habis.pkl`

**Solusi:**
```bash
cd backend/
python3 scripts/train_model.py
```

---


## 📊 Customization

### Ubah Threshold Status Dashboard

Edit `frontend/resources/views/dashboard.blade.php` line ~40:

```php
$kritisDay = 3;  // ATM kritis jika ≤3 hari
$waspDay   = 7;  // ATM waspada jika ≤7 hari
```

### Ubah Tanggal Gajian

Set environment variable sebelum menjalankan pipeline:

```bash
# Tanggal tetap (geser ke Jumat jika weekend)
export PAYDAY_DATE=25

# Atau hari kerja terakhir bulan
export PAYDAY_DATE=last_workday
```

### Ubah / Aktifkan Data Libur Nasional

Secara default sistem memakai daftar libur hardcode. Untuk data akurat dari API:

```bash
# Daftar di https://calendarific.com (tersedia plan gratis)
export CALENDARIFIC_API_KEY=your_api_key_here
export HOLIDAY_COUNTRY=ID
```

Setelah API key di-set, data libur otomatis di-cache ke tabel `holiday_cache` di MySQL — artinya API hanya dipanggil sekali per tahun.

### Jalankan Unit Tests

```bash
cd backend/
python3 -m pytest tests/test_calendar_features.py -v
```

### Ubah Jadwal Scheduler

Edit environment variables:

```bash
export RETRAIN_DAY_OF_WEEK=mon  # Hari retraining
export RETRAIN_HOUR=3           # Jam retraining
```

Atau edit langsung `backend/app/scheduler.py`.

### Ubah Hyperparameter Model

Edit `backend/scripts/train_model.py`:

```python
model = RandomForestRegressor(
    n_estimators=100,    # Jumlah pohon
    max_depth=8,         # Kedalaman maksimal
    random_state=42,
    n_jobs=-1,
)
```

Setelah edit, retrain model: `python3 scripts/train_model.py`

---

## 📈 Model Performance

Typical metrics setelah training:

```
MAE  : ~2.8 hari
R²   : ~0.78
```

**Interpretasi:**
- **MAE (Mean Absolute Error)**: Rata-rata selisih prediksi 2.8 hari dari target business rule
- **R² (R-Squared)**: Model menjelaskan 78% variansi target

**Catatan:** Metrics ini mengukur seberapa baik model meniru rumus bisnis, bukan akurasi terhadap refill events aktual.

---

## 🚦 Production Deployment

### Backend

```bash
# Production mode
uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 2
```

**Atau gunakan systemd service:**

`/etc/systemd/system/prediksi-atm-backend.service`

```ini
[Unit]
Description=Prediksi ATM Backend API
After=network.target mysql.service

[Service]
User=www-data
WorkingDirectory=/path/to/backend
Environment="PATH=/path/to/backend/.venv/bin"
ExecStart=/path/to/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 2
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable prediksi-atm-backend
sudo systemctl start prediksi-atm-backend
```

### Frontend

Gunakan Nginx + PHP-FPM:

```nginx
server {
    listen 80;
    server_name prediksi-atm.yourdomain.com;
    root /path/to/frontend/public;
    
    index index.php;

    location / {
        try_files $uri $uri/ /index.php?$query_string;
    }

    location ~ \.php$ {
        fastcgi_pass unix:/var/run/php/php8.3-fpm.sock;
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
        include fastcgi_params;
    }
}
```

Build production assets:

```bash
cd frontend/
npm run build
php artisan config:cache
php artisan route:cache
php artisan view:cache
```

---

## 📝 Dependensi

### Backend (`requirements.txt`)

```
fastapi==0.141.1
uvicorn==0.52.1
apscheduler==3.11.3
pandas==2.3.3
numpy==2.2.6
scikit-learn==1.7.2
joblib==1.5.3
sqlalchemy==2.0.51
pymysql==2.2.8
requests==2.32.3
```

### Frontend (`composer.json`)

```json
{
  "require": {
    "php": "^8.3",
    "laravel/framework": "^13.8",
    "laravel/tinker": "^3.0"
  }
}
```

### Frontend (`package.json`)

```json
{
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "tailwindcss": "^4.0.0",
    "vite": "^8.0.0",
    "laravel-vite-plugin": "^3.1"
  }
}
```

---

## 📄 License

MIT License

---

## 👥 Contributors

Sistem prediksi ATM berbasis machine learning untuk monitoring dan optimasi operasional ATM.

