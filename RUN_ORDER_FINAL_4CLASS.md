# Urutan Run Final 4 Class

Notebook utama buat jalur final skripsi:

- `MODEL_FINAL_SKRIPSI_4CLASS.ipynb`

Model final operasional terbaru:

- `Hybrid BiLSTM + XGBoost` dengan mode `gated ensemble`

Panduan ini dipakai saat kamu mau:

- rerun notebook dengan urutan yang aman,
- ambil hasil final untuk Bab 4,
- atau siapin demo WebGIS dengan model `4 class`.

## Jalur Paling Aman

Jalankan cell berikut berurutan di `MODEL_BANJIR.ipynb`:

1. `CELL 04 - Model Hybrid Spasial 4 Kelas`
2. `CELL 05 - Visualisasi Korelasi dan Pola Multivariat`
3. `CELL 06 - Analisis Ketimpangan Kelas 4 Kelas`
4. `CELL 07 - Model Hybrid 4 Kelas dengan Rekayasa Fitur`
5. `CELL 22 - Tuning Hyperparameter LSTM + XGBoost (4 Kelas + SMOTE)`
6. `CELL 23 - Seleksi Final Model 4 Kelas`
7. `CELL 09 - Validasi Artefak Model 4 Kelas untuk WebGIS`
8. `CELL 10 - Simulasi Inference 4 Kelas untuk WebGIS`

## Kalau Mau Lebih Cepat

Kalau tidak mau retrain lama di notebook:

1. Jalankan `CELL 04`
2. Jalankan `CELL 07`
3. Lewati `CELL 22`
4. Jalankan `CELL 23`
5. Jalankan `CELL 09`
6. Jalankan `CELL 10`

Catatan:

- Jalur ini lebih cepat, tapi kandidat final bisa kalah rapi dibanding hasil tuning.

## Kalau Mau Sinkron ke Backend WebGIS

Setelah model final sudah dipilih, jalankan dari terminal:

```powershell
python retrain_operational_multiclass_model.py
python webgis_backend.py --export-static-json --no-serve
```

Fungsi dua perintah itu:

- `retrain_operational_multiclass_model.py`: bikin artefak model `4 class` yang dipakai backend.
- `webgis_backend.py --export-static-json --no-serve`: refresh `data/east-jakarta-predictions.json`.

## Scheduler Harian WebGIS

Kalau mau prediksi fallback JSON ikut update otomatis setiap hari:

1. `refresh_daily_predictions.ps1`
2. `install_daily_prediction_scheduler.ps1`

Alurnya:

- `update_openmeteo_dataset_jaktim.py`: update incremental `Master_Data_Spasial_Jaktim_1990_sekarang.csv`
- `refresh_daily_predictions.ps1`: jalankan update dataset lalu export `data/east-jakarta-predictions.json`
- `install_daily_prediction_scheduler.ps1`: daftarkan task harian di Windows Task Scheduler

Contoh preview task tanpa langsung mendaftarkan:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_daily_prediction_scheduler.ps1 -Time 05:30 -AppEnvironment production -PreviewOnly
```

Contoh daftar scheduler harian jam 05:30:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_daily_prediction_scheduler.ps1 -Time 05:30 -AppEnvironment production
```

Contoh run manual sekali untuk tes:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\refresh_daily_predictions.ps1 -AppEnvironment production
```

Catatan:

- Scheduler ini otomatis update dataset cuaca lalu regenerate file fallback JSON setiap hari.
- Kalau source data tidak perlu diambil ulang, pakai `-SkipSourceUpdate`.
- Log setiap run akan masuk ke `artifacts/scheduler_logs/`.

## Scheduler Untuk Deploy Publik

Kalau WebGIS dipublish lewat GitHub -> Railway, gunakan jalur ini:

- `refresh_public_predictions.py`
- `.github/workflows/daily-public-refresh.yml`

Bedanya dengan scheduler lokal:

- scheduler lokal: jalan di Windows Task Scheduler laptop/server Windows
- scheduler publik: jalan di GitHub Actions, lalu commit hasil update ke repo supaya Railway auto-redeploy

Contoh tes lokal runner publik tanpa update sumber:

```powershell
python refresh_public_predictions.py --skip-source-update --app-environment production --app-environment-label PRODUCTION
```

Catatan:

- cron GitHub Actions di-set `21:00 UTC`, setara `04:00 WIB`
- pastikan GitHub Actions repo permission di-set `Read and write`

## Cell Yang Tidak Wajib Untuk Jalur Utama

Bagian ini cuma pembanding/lampiran:

- `CELL 08 - Model Hybrid Biner Multivariat (Pembanding)`
- `CELL 11 - CELL 20` yang isinya eksperimen univariat, threshold tuning biner, dan SMOTE biner
- `CELL 21 - Tabel Pembanding Multikelas vs 2 Kelas (Lampiran Ringkas)`
- `CELL 24 - Catatan Drainase dan Utilitas Terpisah`

## Checklist Sebelum Demo

- Pastikan file `model_bilstm_4class_jaktim.h5` ada
- Pastikan file `model_xgboost_4class_jaktim.pkl` ada
- Pastikan file `scaler_4class_jaktim.pkl` ada
- Pastikan file `daftar_kolom_fitur_4class.pkl` ada
- Pastikan `data/east-jakarta-predictions.json` sudah di-refresh
- Pastikan backend bisa dijalankan tanpa error

## Saran Presentasi

Kalau ditanya dosen, alur paling enak dijelasin:

1. Dataset dan pembagian 4 class
2. Model baseline 4 class
3. Analisis imbalance
4. Perbaikan lewat feature engineering dan tuning
5. Pemilihan model final 4 class
6. Integrasi ke WebGIS
