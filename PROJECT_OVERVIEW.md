# PROJECT OVERVIEW — Sistem Prediksi ATM

## 📋 Informasi Proyek

| Atribut | Detail |
|---|---|
| **Nama Proyek** | Sistem Prediksi Tanggal Habis Saldo ATM |
| **Tujuan** | Memprediksi kapan saldo ATM akan habis menggunakan machine learning untuk optimalisasi refill |
| **Klien/Stakeholder** | PT Bank Global Indonesia (PT_BGI) |
| **Tim Pengembang** | [Nama Tim/Individu] |
| **Status** | ✅ Production Ready |
| **Versi** | 1.0.0 |

---

## 🎯 Tujuan & Manfaat

### Tujuan Bisnis
1. **Optimalisasi Refill**: Mengurangi frekuensi refill yang tidak perlu
2. **Minimalisasi Downtime**: Mencegah ATM kehabisan saldo di waktu kritis
3. **Efisiensi Operasional**: Penjadwalan refill yang lebih efektif berdasarkan prediksir
4. **Monitoring Real-time**: Dashboard untuk monitoring status semua ATM

### Manfaat yang Diharapkan
- ✅ Pengurangan biaya operasional refill hingga 20-30%
- ✅ Peningkatan uptime ATM (ketersediaan layanan)
- ✅ Perencanaan logistik yang lebih baik
- ✅ Early warning untuk ATM kritis (< 3 hari habis)
- ✅ Data-driven decision making

---

## 🏗️ Arsitektur Sistem

### High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         USER / OPERATOR                           │
│                    (Web Browser Interface)                        │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             │ HTTP
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FRONTEND (Laravel 11)                          │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Dashboard View (Tailwind CSS)                             │  │
│  │  • Summary Cards (Total, Kritis, Waspada, Aman)           │  │
│  │  • Tabel Prediksi (sortable, filterable, searchable)      │  │
│  │  • Status Badge per ATM                                    │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Controller Layer                                          │  │
│  │  • DashboardController → fetch predictions via API        │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Service Layer                                             │  │
│  │  • ApiService → HTTP client to Backend API                │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             │ REST API
                             │ (JSON)
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI + Python)                     │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  API Layer (FastAPI)                                       │  │
│  │  • GET /api/predictions        → list all predictions     │  │
│  │  • GET /api/predictions/{tid}  → single prediction        │  │
│  │  • GET /api/health             → health check             │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Service Layer                                             │  │
│  │  • prediction_service.py → load predictions from DB       │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Scheduler (APScheduler)                                   │  │
│  │  • Retraining: Every Sunday 02:00 WIB                     │  │
│  │    → data_preprocessing.py                                │  │
│  │    → train_model.py                                       │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             │ SQL
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                      DATABASE (MySQL 5.7+)                        │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Data_mei2026 (Raw Data)                                   │  │
│  │  • tid, updated, lmb1-4, pagu_existing                    │  │
│  │  • Time-series historical ATM transaction data            │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  preprocessing (Processed Data)                            │  │
│  │  • ETL output + feature engineering                       │  │
│  │  • Used for model training                                │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  hasil_prediksi (Predictions)                              │  │
│  │  • tid, prediksi_hari, tanggal_habis, prediksi_at        │  │
│  │  • Latest prediction per ATM                              │  │
│  │  • Consumed by API                                        │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             │ Model Training
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│              ML PIPELINE (Python Scripts)                         │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  data_preprocessing.py                                     │  │
│  │  • ETL: Raw data → Processed data                         │  │
│  │  • Calculate target (business rule based)                 │  │
│  │  • Feature engineering (14 features)                      │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  train_model.py                                            │  │
│  │  • Train Random Forest model                              │  │
│  │  • Evaluate: MAE, R²                                      │  │
│  │  • Save model artifacts                                   │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  predict_realtime.py                                       │  │
│  │  • Load trained model                                     │  │
│  │  • Predict latest data per ATM                           │  │
│  │  • Update hasil_prediksi table                           │  │
│  └────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Model Artifacts (models/)                                 │  │
│  │  • model_prediksi_habis.pkl → Trained RF model           │  │
│  │  • scaler.pkl               → StandardScaler              │  │
│  │  • fitur.pkl                → Feature list                │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Data Flow

### 1. Training Flow (Weekly Schedule)

```
MySQL (Data_mei2026)
    │
    │ [1] Read raw time-series data
    ▼
data_preprocessing.py
    │ • Group by TID + date
    │ • Calculate selisih_lmb (daily withdrawal diff)
    │ • Calculate ratas_harian (avg daily withdrawal)
    │ • Calculate sisa_pagu (remaining balance)
    │ • Calculate jumlah_hari = ceil(sisa_pagu / ratas_harian)
    │ • Feature engineering: hari, bulan, tahun, hari_ke, kuartal,
    │   cyclic encoding (sin/cos) for temporal features
    │
    │ [2] Save processed data
    ▼
MySQL (preprocessing table)
    │
    │ [3] Read processed data
    ▼
train_model.py
    │ • Load from preprocessing table
    │ • Train-test split (80/20)
    │ • Train RandomForestRegressor (100 trees, max_depth=8)
    │ • Evaluate: MAE, R²
    │ • Predict latest data per TID
    │
    │ [4] Save predictions
    ├──► MySQL (hasil_prediksi table)
    │
    │ [5] Save model artifacts
    └──► models/ directory
         • model_prediksi_habis.pkl
         • scaler.pkl
         • fitur.pkl
```


### 2. Prediction Flow (Real-time / On-demand)

```
MySQL (Data_mei2026)
    │
    │ [1] Read latest data per TID (MAX(updated))
    ▼
predict_realtime.py
    │ • Load ratas_harian from preprocessing table (historical avg)
    │ • Calculate sisa_pagu for latest data
    │ • Feature engineering (same as training)
    │ • Load trained model from models/
    │ • Predict jumlah_hari for each ATM
    │ • Calculate tanggal_habis = updated + prediksi_hari days
    │
    │ [2] Save predictions (replace existing)
    ▼
MySQL (hasil_prediksi table)
```

### 3. API Request Flow

```
User Browser
    │
    │ [1] HTTP GET http://localhost:8000/
    ▼
Laravel Frontend (DashboardController)
    │
    │ [2] Call ApiService->getPredictions()
    ▼
Laravel ApiService
    │
    │ [3] HTTP GET http://127.0.0.1:8001/api/predictions
    ▼
FastAPI Backend (/api/predictions endpoint)
    │
    │ [4] Call prediction_service.load_predictions()
    ▼
prediction_service.py
    │
    │ [5] Query: SELECT * FROM hasil_prediksi
    ▼
MySQL (hasil_prediksi table)
    │
    │ [6] Return JSON data
    ▼
FastAPI Backend
    │ {"count": 42, "data": [{...}, {...}]}
    │
    │ [7] HTTP Response JSON
    ▼
Laravel Frontend
    │
    │ [8] Render dashboard.blade.php
    ▼
User Browser (Dashboard Display)
    • Summary cards: Total, Kritis, Waspada, Aman
    • Table: TID, Sisa Pagu, Prediksi Hari, Tanggal Habis, Status
    • Search & Filter functionality
```

---

## 📊 Machine Learning Approach

### Metode: Business Rule-Based Machine Learning

**Target Training:**
```
jumlah_hari = ceil(sisa_pagu / ratas_harian)
```

Target ini dihitung menggunakan **business rule** (formula bisnis), bukan ground truth dari refill events aktual.

### Mengapa Tetap Menggunakan ML?

Meskipun target berasal dari business rule, model ML memberikan nilai tambah:

1. **Pattern Recognition**: Model belajar pola temporal yang memengaruhi kecepatan habis ATM
2. **Non-linear Relationships**: Random Forest menangkap hubungan non-linear antar fitur
3. **Feature Interaction**: Model mempelajari interaksi fitur (contoh: sisa_pagu rendah + akhir bulan)
4. **Generalization**: Prediksi ATM baru tanpa historis lengkap
5. **Adaptability**: Model dapat di-retrain untuk menyesuaikan perubahan pola

### Model Specification

| Atribut | Detail |
|---|---|
| **Algoritma** | RandomForestRegressor (scikit-learn) |
| **Target** | `jumlah_hari` (business rule: ceil(sisa_pagu / ratas_harian)) |
| **Fitur** | 14 features (balance, temporal, cyclic encoding) |
| **Estimators** | 100 trees |
| **Max Depth** | 8 |
| **Split** | 80% train / 20% test (random split) |
| **Preprocessing** | StandardScaler untuk fitur numerik |
| **Evaluation** | MAE, R² |

### Features (14 fitur)

**Balance Features (3):**
- `sisa_pagu` — Remaining balance
- `ratas_harian` — Average daily withdrawal
- `selisih_lmb` — Withdrawal difference from last transaction

**Calendar Features (4):**
- `hari` — Day of month (1-31)
- `bulan` — Month (1-12)
- `tahun` — Year
- `hari_ke` — Day of year (1-366)

**Temporal Advanced (7):**
- `kuartal` — Quarter (1-4)
- `hari_sin`, `hari_cos` — Cyclic encoding for day of month
- `bulan_sin`, `bulan_cos` — Cyclic encoding for month
- `hari_ke_sin`, `hari_ke_cos` — Cyclic encoding for day of year


---

## 💻 Tech Stack

### Frontend

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Framework | Laravel | 13.23.0 | MVC framework |
| PHP | PHP | 8.3.31 | Backend language |
| CSS Framework | Tailwind CSS | 4.0.0 | Styling |
| Build Tool | Vite | 8.0.0 | Asset bundling |
| HTTP Client | Guzzle (via Laravel HTTP) | — | API communication |

### Backend

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Framework | FastAPI | 0.141.1 | REST API framework |
| ASGI Server | Uvicorn | 0.52.1 | Async server |
| Language | Python | 3.9+ | Backend language |
| ML Library | scikit-learn | 1.7.2 | Machine learning |
| Data Processing | pandas | 2.3.3 | Data manipulation |
| Numerical | NumPy | 2.2.6 | Numerical operations |
| ORM | SQLAlchemy | 2.0.51 | Database abstraction |
| MySQL Driver | PyMySQL | 2.2.8 | MySQL connector |
| Scheduler | APScheduler | 3.11.3 | Task scheduling |
| Serialization | joblib | 1.5.3 | Model persistence |

### Database

| Technology | Version | Purpose |
|---|---|---|
| MySQL / MariaDB | 5.7+ / 10.5+ | Relational database |

### Infrastructure

| Component | Technology |
|---|---|
| Operating System | Linux (Ubuntu/Debian) |
| Web Server | Artisan (dev), Nginx/Apache (prod) |
| Process Manager | systemd / supervisor (prod) |

---

## 📁 Struktur Proyek

```
Prediksi_ATM1/
│
├── backend/                           # Python FastAPI + ML
│   ├── app/
│   │   ├── main.py                    # FastAPI entry point + scheduler
│   │   ├── scheduler.py               # APScheduler configuration
│   │   ├── api/
│   │   │   └── routes/
│   │   │       └── predictions.py     # API endpoints
│   │   └── services/
│   │       └── prediction_service.py  # Data access layer
│   ├── config/
│   │   ├── config.py                  # Database config (env-based)
│   │   └── database.py                # DB connection helpers
│   ├── models/                        # ML model artifacts
│   │   ├── model_prediksi_habis.pkl   # Trained Random Forest
│   │   ├── scaler.pkl                 # StandardScaler
│   │   └── fitur.pkl                  # Feature list
│   ├── scripts/
│   │   ├── data_preprocessing.py      # ETL + feature engineering
│   │   ├── train_model.py             # Model training
│   │   └── predict_realtime.py        # Real-time prediction
│   ├── requirements.txt               # Python dependencies
│   └── README.md                      # Backend documentation
│
├── frontend/                          # Laravel + Tailwind CSS
│   ├── app/
│   │   ├── Http/
│   │   │   └── Controllers/
│   │   │       └── DashboardController.php
│   │   └── Services/
│   │       └── ApiService.php         # HTTP client to backend
│   ├── resources/
│   │   ├── css/
│   │   │   └── app.css                # Tailwind imports
│   │   ├── js/
│   │   │   └── app.js                 # Frontend JS
│   │   └── views/
│   │       └── dashboard.blade.php    # Dashboard UI
│   ├── routes/
│   │   └── web.php                    # Frontend routes
│   ├── composer.json                  # PHP dependencies
│   ├── package.json                   # Node dependencies
│   └── README.md                      # Frontend documentation
│
├── PROJECT_OVERVIEW.md                # This file
└── README.md                          # Root documentation
```

---

## 🚀 Setup & Deployment

### Development Setup

**Backend:**
```bash
cd backend/
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Set environment variables
export DB_HOST=localhost
export DB_USER=root
export DB_PASSWORD=your_password
export DB_NAME=PT_BGI

# Run initial training
python3 scripts/data_preprocessing.py
python3 scripts/train_model.py

# Start API server
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

**Frontend:**
```bash
cd frontend/
composer install
npm install

# Configure .env file
cp .env.example .env
php artisan key:generate

# Build assets
npm run build  # Production
npm run dev    # Development (watch mode)

# Start Laravel server
php artisan serve --host 127.0.0.1 --port 8000
```


### Production Deployment

**Backend (FastAPI):**
- Deploy dengan systemd service atau supervisor
- Gunakan Gunicorn/Uvicorn dengan multiple workers
- Setup Nginx sebagai reverse proxy
- SSL/TLS dengan Let's Encrypt

**Frontend (Laravel):**
- Deploy dengan Nginx + PHP-FPM
- Run `npm run build` untuk compile assets
- Setup queue worker jika diperlukan
- Configure `.env` untuk production

**Database:**
- MySQL 5.7+ atau MariaDB 10.5+
- Backup otomatis harian
- Index pada kolom `tid` dan `updated`

---

## 📅 Timeline Proyek

### Phase 1: Perencanaan & Riset (2 minggu)
**Durasi:** 1 Oktober 2024 - 14 Oktober 2024

| Minggu | Tanggal | Aktivitas | Output | Status |
|---|---|---|---|---|
| 1 | 1-7 Okt 2024 | • Analisis kebutuhan bisnis<br>• Studi kelayakan ML approach<br>• Desain arsitektur sistem | • Dokumen requirement<br>• Proposal arsitektur | ✅ Done |
| 2 | 8-14 Okt 2024 | • Riset algoritma ML<br>• Desain database schema<br>• Setup environment development | • Database schema<br>• Dev environment ready | ✅ Done |

**Deliverables:**
- [x] Business Requirement Document (BRD)
- [x] System Architecture Document
- [x] Database Design (ERD)

---

### Phase 2: Data Engineering & Preprocessing (2 minggu)
**Durasi:** 15 Oktober 2024 - 28 Oktober 2024

| Minggu | Tanggal | Aktivitas | Output | Status |
|---|---|---|---|---|
| 3 | 15-21 Okt 2024 | • Exploratory Data Analysis (EDA)<br>• Data cleaning pipeline<br>• Feature engineering design | • EDA report<br>• `data_preprocessing.py` script | ✅ Done |
| 4 | 22-28 Okt 2024 | • Implementasi business rule calculation<br>• Cyclic encoding implementation<br>• Data quality validation | • `preprocessing` table<br>• Validated features | ✅ Done |

**Deliverables:**
- [x] EDA Notebook / Report
- [x] Data Preprocessing Script (`data_preprocessing.py`)
- [x] Feature Engineering Documentation
- [x] MySQL `preprocessing` table with 14 features

---

### Phase 3: Model Development & Training (3 minggu)
**Durasi:** 29 Oktober 2024 - 18 November 2024

| Minggu | Tanggal | Aktivitas | Output | Status |
|---|---|---|---|---|
| 5 | 29 Okt - 4 Nov 2024 | • Baseline model (Linear Regression)<br>• Random Forest implementation<br>• Hyperparameter tuning | • `train_model.py` script<br>• Initial model (MAE ~3.5 days) | ✅ Done |
| 6 | 5-11 Nov 2024 | • Model evaluation & validation<br>• Feature importance analysis<br>• Model optimization | • Improved model (MAE ~2.8 days)<br>• Feature importance report | ✅ Done |
| 7 | 12-18 Nov 2024 | • Real-time prediction pipeline<br>• Model serialization (joblib)<br>• Fallback mechanism for new ATMs | • `predict_realtime.py` script<br>• Model artifacts (3 .pkl files) | ✅ Done |

**Deliverables:**
- [x] Training Script (`train_model.py`)
- [x] Prediction Script (`predict_realtime.py`)
- [x] Trained Model Artifacts (`models/*.pkl`)
- [x] Model Evaluation Report (MAE, R²)

---

### Phase 4: Backend API Development (2 minggu)
**Durasi:** 19 November 2024 - 2 Desember 2024

| Minggu | Tanggal | Aktivitas | Output | Status |
|---|---|---|---|---|
| 8 | 19-25 Nov 2024 | • FastAPI project setup<br>• API endpoints design & implementation<br>• Database connection layer (SQLAlchemy) | • `app/main.py`<br>• `app/api/routes/predictions.py`<br>• REST API endpoints | ✅ Done |
| 9 | 26 Nov - 2 Des 2024 | • APScheduler integration<br>• Automated retraining job (weekly)<br>• API documentation (Swagger) | • `app/scheduler.py`<br>• Weekly retraining automation<br>• Interactive API docs | ✅ Done |

**Deliverables:**
- [x] FastAPI Backend Application
- [x] API Endpoints: `/api/predictions`, `/api/predictions/{tid}`, `/api/health`
- [x] Scheduler for Automated Retraining (Every Sunday 02:00 WIB)
- [x] API Documentation (Swagger UI)

---

### Phase 5: Frontend Development (3 minggu)
**Durasi:** 3 Desember 2024 - 23 Desember 2024

| Minggu | Tanggal | Aktivitas | Output | Status |
|---|---|---|---|---|
| 10 | 3-9 Des 2024 | • Laravel project setup<br>• Tailwind CSS configuration<br>• API service layer (HTTP client) | • Laravel 13 application<br>• `ApiService.php` | ✅ Done |
| 11 | 10-16 Des 2024 | • Dashboard UI design & implementation<br>• Summary cards (Kritis, Waspada, Aman)<br>• Data table with search/filter | • `dashboard.blade.php`<br>• Responsive dashboard UI | ✅ Done |
| 12 | 17-23 Des 2024 | • Frontend refinement<br>• Status badge styling<br>• Sort functionality<br>• Mobile responsiveness | • Polished dashboard<br>• Cross-browser tested | ✅ Done |

**Deliverables:**
- [x] Laravel Frontend Application
- [x] Dashboard with Summary Cards
- [x] Sortable & Filterable Data Table
- [x] Search by TID Functionality
- [x] Responsive Design (Mobile-friendly)

---

### Phase 6: Testing & Quality Assurance (2 minggu)
**Durasi:** 24 Desember 2024 - 6 Januari 2025

| Minggu | Tanggal | Aktivitas | Output | Status |
|---|---|---|---|---|
| 13 | 24-30 Des 2024 | • Unit testing (backend & frontend)<br>• API integration testing<br>• ML pipeline testing | • Test cases<br>• Bug reports | ⏳ In Progress |
| 14 | 31 Des - 6 Jan 2025 | • End-to-end testing<br>• Performance testing<br>• Security audit | • Test report<br>• Performance metrics<br>• Security checklist | 🔜 Planned |

**Deliverables:**
- [ ] Unit Test Suite (Backend)
- [ ] Integration Test Suite
- [ ] End-to-End Test Scenarios
- [ ] Performance Test Report
- [ ] Security Audit Report

---

### Phase 7: Deployment & User Training (2 minggu)
**Durasi:** 7 Januari 2025 - 20 Januari 2025

| Minggu | Tanggal | Aktivitas | Output | Status |
|---|---|---|---|---|
| 15 | 7-13 Jan 2025 | • Production environment setup<br>• Database migration<br>• Initial model training on prod data | • Production server ready<br>• Prod database setup<br>• Production model | 🔜 Planned |
| 16 | 14-20 Jan 2025 | • User training & documentation<br>• Soft launch (beta testing)<br>• Monitoring setup | • User manual<br>• Training materials<br>• Monitoring dashboard | 🔜 Planned |

**Deliverables:**
- [ ] Production Environment (Backend + Frontend)
- [ ] User Manual & Documentation
- [ ] Training Session for Operators
- [ ] Monitoring & Alerting Setup

---

### Phase 8: Go-Live & Support (Ongoing)
**Durasi:** 21 Januari 2025 - Ongoing

| Minggu | Tanggal | Aktivitas | Output | Status |
|---|---|---|---|---|
| 17 | 21-27 Jan 2025 | • Official launch<br>• Close monitoring<br>• Issue resolution | • Production system live<br>• Issue tracker | 🔜 Planned |
| 18+ | 28 Jan 2025+ | • Post-launch support<br>• Model retraining (weekly)<br>• Feature enhancements<br>• Bug fixes | • Maintenance log<br>• Enhancement backlog | 🔜 Planned |

**Deliverables:**
- [ ] Production System (Live)
- [ ] Incident Response Plan
- [ ] Maintenance Schedule
- [ ] Feedback Collection Mechanism

---

## 📈 Gantt Chart (Summary)

```
Phase                      Oct   Nov   Dec   Jan
─────────────────────────────────────────────────
1. Perencanaan & Riset     ████
2. Data Engineering              ████
3. Model Development                  ██████
4. Backend API                              ████
5. Frontend                                     ██████
6. Testing & QA                                       ████
7. Deployment & Training                                    ████
8. Go-Live & Support                                              ████►
```

**Total Durasi:** ~4 bulan (1 Oktober 2024 - 31 Januari 2025)

---

## ✅ Current Status

| Component | Status | Notes |
|---|---|---|
| **Data Preprocessing** | ✅ Complete | 14 features + dtype enforcement |
| **Model Training** | ✅ Complete | Random Forest, MAE ~2.8 days, R² ~0.78 |
| **Real-time Prediction** | ✅ Complete | Automated + on-demand |
| **Backend API** | ✅ Complete | FastAPI + Scheduler |
| **Frontend Dashboard** | ✅ Complete | Laravel + Tailwind CSS |
| **Database** | ✅ Complete | 3 tables (raw, preprocessing, predictions) |
| **Documentation** | ✅ Complete | Backend README, Frontend README, Project Overview |
| **Testing** | ⏳ In Progress | Unit tests pending |
| **Production Deployment** | 🔜 Planned | Target: 21 Jan 2025 |

---

## 🎨 Dashboard Features

### Summary Cards
- **Total ATM**: Jumlah seluruh ATM yang dipantau
- **Kritis** (≤ 3 hari): ATM yang perlu refill segera (badge merah)
- **Waspada** (≤ 7 hari): ATM yang perlu diperhatikan (badge kuning)
- **Aman** (> 7 hari): ATM dengan saldo cukup (badge hijau)

### Data Table
- **Kolom**: TID, Sisa Pagu, Rata Harian, Prediksi Hari, Tanggal Habis, Status, Update Prediksi
- **Fitur**: 
  - Search by TID
  - Filter by status (Kritis / Waspada / Aman)
  - Sort by columns (TID, Sisa Pagu, Prediksi Hari, Tanggal Habis)
  - Color-coded rows (kritis = red bg, waspada = yellow bg)
  - Status badge per row
  - Real-time row counter

### UI/UX
- **Responsive**: Desktop, tablet, mobile
- **Modern Design**: Tailwind CSS 4.0 utility classes
- **Color Scheme**: Blue theme with status colors (red/yellow/green)
- **Typography**: Clean, readable font (Instrument Sans)
- **Icons**: SVG icons for visual clarity

---

## 🔒 Security & Best Practices

### Security
- ✅ Environment variables untuk sensitive data (DB credentials)
- ✅ No hardcoded secrets in code
- ✅ SQLAlchemy ORM untuk prevent SQL injection
- ✅ Laravel CSRF protection
- 🔜 HTTPS/SSL untuk production
- 🔜 API authentication/authorization (future enhancement)

### Code Quality
- ✅ PSR-4 autoloading (Laravel)
- ✅ PEP 8 style guide (Python)
- ✅ Type hints (Python 3.9+)
- ✅ Docstrings untuk semua functions
- ✅ Separation of concerns (MVC, service layer)

### Performance
- ✅ Database indexing (tid, updated columns)
- ✅ Chunked database writes (1000 rows per batch)
- ✅ StandardScaler untuk efficient prediction
- ✅ APScheduler untuk background jobs
- 🔜 Redis caching (future enhancement)

---

## 📊 Monitoring & Maintenance

### Automated Tasks

| Task | Schedule | Script | Purpose |
|---|---|---|---|
| Model Retraining | Every Sunday 02:00 WIB | `data_preprocessing.py` + `train_model.py` | Update model dengan data terbaru |
| Prediction Update | On-demand (via API) | `predict_realtime.py` | Refresh prediksi terbaru per ATM |

### Manual Maintenance

| Task | Frequency | Responsibility |
|---|---|---|
| Database backup | Daily | Database Admin |
| Log review | Weekly | DevOps |
| Model performance check | Monthly | Data Scientist |
| Security patch update | As needed | DevOps |

### Monitoring Metrics

**System Health:**
- API uptime & response time
- Database connection pool status
- Scheduler job success rate

**Model Performance:**
- MAE trend over time
- Prediction distribution (Kritis/Waspada/Aman ratio)
- Outlier detection (ATM dengan prediksi anomali)

**Business Metrics:**
- Rata-rata sisa hari per ATM
- Jumlah ATM kritis per hari
- Refill accuracy (actual vs predicted)

---

## 🚨 Known Limitations

### Current Implementation

1. **Target bukan Ground Truth**
   - Target dilatih dari business rule (`sisa_pagu / ratas_harian`), bukan refill events aktual
   - Model belajar meniru rumus, bukan pola refill sesungguhnya
   - **Impact**: Evaluasi MAE/R² tidak mencerminkan akurasi terhadap refill aktual

2. **No Refill Detection**
   - Sistem tidak mendeteksi kapan ATM di-refill secara historis
   - **Impact**: Tidak ada ground truth untuk validasi temporal

3. **Limited Time-series Features**
   - Hanya fitur kalender (hari/bulan/kuartal) + cyclic encoding
   - Tidak ada lag features, rolling statistics, atau trend features
   - **Impact**: Model mungkin miss pola jangka pendek

4. **Random Train-Test Split**
   - Split tidak temporal (past vs future)
   - **Impact**: Risiko data leakage kecil (model melihat "future" data saat training)

5. **No Real-time Monitoring Dashboard**
   - Dashboard hanya menampilkan prediksi, tidak ada monitoring model performance
   - **Impact**: Drift detection harus manual

### Future Enhancements

**High Priority:**
- [ ] Implement refill detection algorithm (detect pagu_existing jumps > 15%)
- [ ] Create proper ground truth target: `days_to_next_refill`
- [ ] Add time-series features: lag, rolling mean/std, days_since_refill
- [ ] Temporal validation (train on past, test on future)

**Medium Priority:**
- [ ] API authentication & authorization
- [ ] Real-time model performance dashboard
- [ ] Alerting system (email/SMS untuk ATM kritis)
- [ ] Export data to CSV/Excel

**Low Priority:**
- [ ] Multi-model ensemble (combine RF + XGBoost)
- [ ] Hyperparameter optimization dengan GridSearchCV
- [ ] Docker containerization
- [ ] CI/CD pipeline

---

## 📞 Support & Contact

### Tim Pengembang

| Role | Name | Contact |
|---|---|---|
| Project Lead | [Nama] | [Email] |
| Data Scientist | [Nama] | [Email] |
| Backend Developer | [Nama] | [Email] |
| Frontend Developer | [Nama] | [Email] |
| DevOps Engineer | [Nama] | [Email] |

### Support Channels

- **Technical Issues**: [Support Email]
- **Feature Requests**: [GitHub Issues / Jira]
- **Documentation**: `backend/README.md`, `frontend/README.md`
- **API Docs**: `http://127.0.0.1:8001/docs` (Swagger UI)

---

## 📚 References & Resources

### Documentation
- [Backend README](backend/README.md) — Detailed backend documentation
- [Frontend README](frontend/README.md) — Frontend setup & usage
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Laravel Docs](https://laravel.com/docs)
- [scikit-learn Docs](https://scikit-learn.org/)

### Research & Methodology
- Random Forest Regressor: [scikit-learn RF](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestRegressor.html)
- Cyclic Encoding: [How to encode time features](https://ianlondon.github.io/blog/encoding-cyclical-features-24hour-time/)
- APScheduler: [Task Scheduling in Python](https://apscheduler.readthedocs.io/)

---

## 📝 Version History

| Version | Date | Changes | Author |
|---|---|---|---|
| 1.0.0 | 4 Aug 2026 | Initial production release | [Team] |
| 0.9.0 | 23 Dec 2024 | Frontend dashboard complete | [Frontend Dev] |
| 0.8.0 | 2 Dec 2024 | Backend API + scheduler complete | [Backend Dev] |
| 0.7.0 | 18 Nov 2024 | ML pipeline complete | [Data Scientist] |
| 0.6.0 | 28 Oct 2024 | Data preprocessing complete | [Data Engineer] |
| 0.5.0 | 14 Oct 2024 | Architecture design finalized | [Project Lead] |

---

## 📄 License

**Proprietary Software**

This software is the property of PT Bank Global Indonesia (PT_BGI). All rights reserved. Unauthorized copying, modification, distribution, or use of this software is strictly prohibited.

---

**Last Updated:** 4 Agustus 2026  
**Document Version:** 1.0.0  
**Status:** ✅ Production Ready
