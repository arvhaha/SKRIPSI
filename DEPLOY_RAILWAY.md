# Deploy FloodGIS ke Railway

File ini untuk publish WebGIS supaya bisa diakses orang lain lewat URL publik.

Checklist aktivasi GitHub Actions + Railway yang lebih operasional ada di:

- `CHECKLIST_AKTIVASI_GITHUB_ACTIONS_RAILWAY.md`

## Kenapa Railway

- Paling cocok untuk project ini karena backend Python, frontend statis, dan file model ada dalam satu repo.
- Railway menyediakan domain publik dan HTTPS.
- Railway bisa deploy langsung dari GitHub atau dari Dockerfile.

## File yang sudah disiapkan

- `webgis_backend.py`
  Sudah membaca `HOST` dan `PORT` dari environment.
- `requirements.txt`
  Berisi dependency inti backend.
- `Dockerfile`
  Supaya environment deploy lebih konsisten untuk TensorFlow + XGBoost.
- `.dockerignore`
  Mengurangi file yang tidak perlu saat build image.
- `.github/workflows/daily-public-refresh.yml`
  Scheduler publik harian via GitHub Actions untuk update dataset dan prediksi.

## Langkah deploy

1. Push project ini ke GitHub.
2. Buka Railway dan buat project baru.
3. Pilih `Deploy from GitHub repo`.
4. Pilih repo skripsi/webgis kamu.
5. Railway akan mendeteksi `Dockerfile` dan build otomatis.
6. Setelah deploy sukses, buka service kamu.
7. Masuk ke `Settings` -> `Networking` -> `Public Networking`.
8. Klik `Generate Domain`.
9. Railway akan memberikan URL publik seperti `https://namaservice.up.railway.app`.
10. Isi juga `ADMIN_USERNAME` dan `ADMIN_PASSWORD` supaya halaman admin tidak terbuka bebas saat publish.

## Hal penting

- Pastikan file berikut ikut ter-push:
  - `model_bilstm_4class_jaktim.h5`
  - `model_xgboost_4class_jaktim.pkl`
  - `scaler_4class_jaktim.pkl`
  - `daftar_kolom_fitur_4class.pkl`
  - `Master_Data_Spasial_Jaktim_1990_sekarang.csv`
  - folder `data/`
- Kalau build gagal karena memory atau waktu build terlalu besar, opsi berikut biasanya paling membantu:
  - pakai plan Railway yang lebih kuat
  - kecilkan file yang tidak perlu di repo
  - pindahkan notebook dan artefak eksperimen besar di luar repo deploy

## Setelah deploy

- Homepage publik: `/`
- Admin page: `/admin.html`
  - Di mode production, halaman ini perlu Basic Auth dan akan dinonaktifkan kalau credential admin belum diisi.
- API health check: `/api/health`
- API predictions: `/api/predictions`

## Scheduler Untuk Server Publik

Kalau deploy publik memakai GitHub -> Railway, scheduler paling aman bukan Windows Task Scheduler lokal, tetapi workflow GitHub Actions:

- workflow: `.github/workflows/daily-public-refresh.yml`
- runner lintas platform: `refresh_public_predictions.py`

Cara kerjanya:

1. GitHub Actions jalan setiap hari jam `04:00 WIB` (`21:00 UTC` di cron workflow).
2. Workflow update `Master_Data_Spasial_Jaktim_1990_sekarang.csv` dari Open-Meteo.
3. Workflow regenerate `data/east-jakarta-predictions.json`.
4. Workflow commit hasil terbaru ke repo.
5. Railway auto-redeploy dari commit tersebut, sehingga server publik ikut memakai data baru.

Hal yang perlu dipastikan di GitHub:

- repo Actions permission harus `Read and write`
- Railway service harus auto-deploy dari branch yang sama dengan workflow
- file model dan dataset utama memang ada di repo yang dideploy

Kalau mau tes manual tanpa menunggu jam cron, buka tab `Actions` di GitHub lalu jalankan `Daily Public Prediction Refresh` lewat tombol `Run workflow`.

## Catatan

Arsitektur sekarang masih cocok untuk demo, skripsi, dan trafik ringan. Kalau nanti mau dipakai lebih serius, langkah berikutnya yang bagus adalah memindahkan server ini ke framework seperti FastAPI atau Flask + reverse proxy.
