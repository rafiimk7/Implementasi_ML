# Prediksi ATM

Project full-stack untuk sistem prediksi tanggal habis saldo ATM, terdiri dari:

- Backend: FastAPI + Python + scheduler otomatis
- Frontend: Laravel + Blade + Vite
- Database: MySQL untuk backend dan SQLite default untuk Laravel frontend

Arsitektur dasar:

- Backend berjalan di `http://127.0.0.1:8001`
- Frontend Laravel berjalan di `http://127.0.0.1:8000`
- Frontend memanggil API backend melalui URL `http://127.0.0.1:8001`

> Catatan: README ini sudah disesuaikan dengan implementasi yang ada saat ini. Semuanya dapat dijalankan bila environment MySQL, Python, Composer, dan Node sudah siap, serta model ML sudah dibuat terlebih dahulu.

---

## 1. Persyaratan sistem

Pastikan perangkat Anda sudah memiliki:

- Python 3.10+
- pip
- venv
- Composer
- Node.js + npm
- MySQL/MariaDB (untuk backend ML dan data prediksi)
- Git (opsional)

Cek versi:

```bash
python3 --version
composer --version
node -v
npm -v
mysql --version
```

---

## 2. Clone project

```bash
cd ~/Projects
git clone <URL_REPOSITORY>
cd Prediksi_ATM1
```

---

## 3. Setup backend Python (FastAPI)

Masuk ke folder backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Jika Anda sudah memiliki virtual environment, cukup aktifkan:

```bash
cd backend
source .venv/bin/activate
```

### 3.1 Konfigurasi environment backend

Salin file contoh env:

```bash
cp .env.example .env
```

Edit file `.env` dan sesuaikan konfigurasi database serta parameter ML:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password_here
DB_NAME=PT_BGI

SOURCE_TABLE=data_mei2026
PAYDAY_DATE=25
CALENDARIFIC_API_KEY=your_calendarific_api_key_here
HOLIDAY_COUNTRY=ID
PREDICT_INTERVAL_MINUTES=15
PREDICT_WINDOW_DAYS=31
RETRAIN_DAY_OF_WEEK=sun
RETRAIN_HOUR=2
```

Catatan:

- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` harus sesuai database MySQL Anda.
- `SOURCE_TABLE` adalah tabel data ATM yang akan diproses.
- `CALENDARIFIC_API_KEY` dapat dikosongkan jika tidak dipakai; sistem akan fallback ke data libur lokal.

---

## 4. Jalankan pipeline data dan model backend

Sebelum menjalankan API, pastikan database MySQL sudah dibuat dan user punya hak akses. Lalu jalankan proses preprocessing dan training model satu kali untuk menghasilkan model ML yang dibutuhkan:

```bash
cd backend
source .venv/bin/activate

python3 scripts/data_preprocessing.py
python3 scripts/train_model.py
```

Model hasil training akan disimpan di folder `backend/models`, yang selanjutnya dipakai oleh script prediksi realtime. Setelah itu, backend siap menerima request.

> Pada implementasi saat ini, scheduler otomatis juga akan menjalankan preprocessing dan prediksi berkala saat API start. Aktivasi manual di bawah ini tetap bisa dilakukan untuk kebutuhan testing atau debugging.

---

## 5. Jalankan backend FastAPI

Jalankan server backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Saat API mulai, scheduler otomatis akan berjalan dari [backend/app/main.py](backend/app/main.py) dan [backend/app/scheduler.py](backend/app/scheduler.py). Scheduler ini akan menjalankan prediksi realtime tiap interval tertentu dan retraining mingguan sesuai konfigurasi `.env`.

Setelah server berhasil dijalankan, cek:

- Swagger UI: `http://127.0.0.1:8001/docs`
- Root endpoint: `http://127.0.0.1:8001/`
- Health API: `http://127.0.0.1:8001/api/health`

Jika ingin berjalan tanpa reload:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

---

## 6. Setup frontend Laravel

Masuk ke folder frontend:

```bash
cd frontend
composer install
```

Salin file env laravel:

```bash
cp .env.example .env
```

Generate APP key:

```bash
php artisan key:generate
```

### 6.1 Setup database frontend

Project Laravel ini default memakai SQLite untuk session dan lokal, jadi buat file database SQLite jika belum ada:

```bash
touch database/database.sqlite
php artisan migrate
```

Jika Anda ingin menggunakan database MySQL untuk Laravel, sesuaikan `.env` di frontend sesuai kebutuhan.

### 6.2 Install dependency frontend

```bash
npm install
npm run build
```

---

## 7. Jalankan frontend Laravel

```bash
cd frontend
php artisan serve --host 127.0.0.1 --port 8000
```

Akses browser ke:

```text
http://127.0.0.1:8000
```

Jika ingin dibangun dengan Vite dev server:

```bash
npm run dev
```

---

## 8. Jalankan dua service secara bersamaan

Biasanya backend dan frontend dijalankan dalam terminal yang berbeda.

Terminal 1 (backend):

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Terminal 2 (frontend):

```bash
cd frontend
php artisan serve --host 127.0.0.1 --port 8000
```

---

## 9. Script tambahan yang berguna

### Prediksi realtime manual

```bash
cd backend
source .venv/bin/activate
python3 scripts/predict_realtime.py
```

### Menjalankan semua setup sekaligus (opsional)

Jika Anda ingin setup cepat dan project sudah memiliki MySQL dan environment backend siap:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 scripts/data_preprocessing.py
python3 scripts/train_model.py
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Di terminal lain:

```bash
cd frontend
composer install
cp .env.example .env
php artisan key:generate
touch database/database.sqlite
php artisan migrate
npm install
npm run build
php artisan serve --host 127.0.0.1 --port 8000
```

---

## 10. Troubleshooting umum

### Backend tidak bisa berjalan

- Pastikan `source .venv/bin/activate` sudah dijalankan.
- Pastikan MySQL aktif dan `.env` backend benar.
- Pastikan package Python sudah terinstall: `pip install -r requirements.txt`.
- Cek apakah port `8001` sudah dipakai oleh proses lain.

### Frontend tidak bisa load

- Pastikan Composer dependency sudah terinstall: `composer install`.
- Pastikan `php artisan key:generate` sudah dijalankan.
- Pastikan `database/database.sqlite` ada.
- Pastikan `npm install` dan `npm run build` sudah selesai.

### API tidak bisa diakses oleh Laravel

- Pastikan backend berjalan di `127.0.0.1:8001`.
- Cek `frontend/app/Services/ApiService.php` dan pastikan base URL sesuai.

---

## 11. Struktur folder penting

```text
Prediksi_ATM1/
├── backend/
│   ├── app/
│   ├── config/
│   ├── scripts/
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── app/
│   ├── resources/
│   ├── routes/
│   ├── composer.json
│   └── .env.example
├── DOKUMENTASI TEKNIS.md
└── README.md
```

---

## 12. Kesimpulan

Untuk menjalankan project ini dengan benar, langkah utama adalah:

1. Install dependency Python backend
2. Setup `.env` backend dan MySQL
3. Jalankan preprocessing + training model
4. Jalankan FastAPI di port 8001
5. Install dependency frontend Laravel
6. Setup `.env` frontend
7. Jalankan `php artisan serve` di port 8000

Jika semua langkah di atas berhasil, aplikasi siap digunakan.
