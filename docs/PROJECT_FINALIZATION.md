# Finalisasi Arsitektur Proyek ATM Prediction

## 1. Scope final proyek

Proyek ini sudah memiliki arsitektur pipeline yang konsisten untuk prediksi tanggal habis ATM, dengan pembagian tugas yang jelas antara:

- data sumber raw: tabel MySQL `data_2026`
- preprocessing: tabel `preprocessing`
- hasil prediksi: tabel `hasil_prediksi`
- model: artefak di folder `backend/models`
- dokumentasi evaluasi: folder `backend/visualizations/reports`

## 2. Sumber data dan tabel

### Tabel sumber raw
- Nama tabel: `data_2026`
- Fungsi: data historis ATM yang dipakai sebagai input utama
- Struktur umum:
  - `tid`
  - `updated`
  - `lmb1`, `lmb2`, `lmb3`, `lmb4`
  - `pagu_existing`

### Tabel preprocessing
- Nama tabel: `preprocessing`
- Fungsi: hasil feature engineering dan target business rule siap training
- Berisi fitur seperti:
  - `sisa_pagu`, `ratas_harian`, `selisih_lmb`
  - `is_weekend`, `is_payday`, `is_holiday`
  - `days_to_payday`, `days_since_payday`
  - `trend_7d_ratio`, `rolling_7d_ratio`
  - `jumlah_hari`

### Tabel hasil prediksi
- Nama tabel: `hasil_prediksi`
- Fungsi: output prediksi realtime untuk dashboard
- Kolom utama:
  - `tid`
  - `updated`
  - `sisa_pagu`
  - `ratas_harian`
  - `prediksi_hari`
  - `tanggal_habis`
  - `threshold`
  - `prediksi_at`

## 3. Flow data yang jelas

### A. Data ingestion ke preprocessing
File yang bertanggung jawab:
- [backend/scripts/data_preprocessing.py](../backend/scripts/data_preprocessing.py)

Alur:
1. Baca data raw dari `data_2026`
2. Validasi tipe data dan tanggal
3. Hitung agregasi harian per ATM
4. Hitung saldo sisa, rata-rata harian, dan trend historis
5. Tambahkan fitur kalender seperti weekend, gajian, tanggal merah
6. Hitung target `jumlah_hari` dengan business rule
7. Simpan ke tabel `preprocessing`

### B. Training model
File yang bertanggung jawab:
- [backend/scripts/train_model.py](../backend/scripts/train_model.py)

Alur:
1. Baca `preprocessing`
2. Validasi target dan cleanup data
3. Split data per TID berdasarkan urutan waktu
4. Scaling fitur dengan `StandardScaler`
5. Training model regressor (LightGBM fallback ke RandomForest)
6. Evaluasi dengan MAE, R², MAPE
7. Simpan model ke `backend/models`
8. Simpan hasil evaluasi ke `backend/visualizations/reports`

### C. Prediksi realtime
File yang bertanggung jawab:
- [backend/scripts/predict_realtime.py](../backend/scripts/predict_realtime.py)

Alur:
1. Baca `preprocessing` untuk 1 baris terbaru per TID
2. Validasi fitur yang dibutuhkan model
3. Load model + scaler
4. Prediksi `prediksi_hari`
5. Terapkan aturan status tunggal `status_from_hari()`
6. Simpan/UPSERT ke `hasil_prediksi`

### D. Scheduler otomatis
File yang bertanggung jawab:
- [backend/app/scheduler.py](../backend/app/scheduler.py)

Fungsi scheduler:
- prediksi realtime berkala
- retraining mingguan penuh
- refresh hasil prediksi setelah retraining

## 4. Aturan bisnis yang dijadikan source of truth

Status harus mengikuti satu fungsi tunggal agar konsisten di backend dan dashboard:

- `status_from_hari(hari)`

Aturan final:
- `<= 1 hari` -> `🔴 Kritis`
- `2 sampai 3 hari` -> `🟠 Waspada`
- `> 3 hari` -> `🟢 Aman`

Ini sudah dibuat untuk menghindari masalah mismatch label yang sebelumnya muncul karena parsing string berbeda-beda di layer yang berbeda.

## 5. Standar machine learning yang sudah dipenuhi

Proyek ini sudah mengadopsi praktik ML yang umum, yaitu:

- target jelas: `jumlah_hari`
- feature engineering di preprocessing
- validasi target terhadap business rule
- split waktu per TID, bukan split acak
- scaling fitur sebelum training
- model regressor yang umum digunakan (LightGBM/RandomForest)
- evaluasi numerik: MAE, R², MAPE
- pembagian artefak model dan report evaluasi
- prediksi real-time menggunakan model yang sama dengan file yang sudah dilatih

## 6. Praktik yang direkomendasikan untuk finalisasi lanjutan

1. Tetap gunakan `status_from_hari()` sebagai satu-satunya sumber label status.
2. Konsisten gunakan `preprocessing` sebagai satu sumber feature untuk semua proses training dan realtime.
3. Hindari parsing label status dari string tabel di frontend karena rentan mismatch.
4. Simpan hasil evaluasi setiap kali training dilakukan.
5. Pastikan scheduler dan manual run selalu mengarah ke flow yang sama.

## 7. Kesimpulan

Struktur proyek sudah berada pada taraf yang layak untuk finalisasi, karena:

- fungsi dan tabel sudah terhubung secara logis
- source of truth untuk status sudah dipusatkan
- flow data dari raw -> preprocessing -> training -> prediction -> dashboard sudah jelas
- proses training mengikuti praktik machine learning yang standard

Dengan demikian, pipeline siap digunakan sebagai baseline yang konsisten untuk pengembangan model ke depan.
