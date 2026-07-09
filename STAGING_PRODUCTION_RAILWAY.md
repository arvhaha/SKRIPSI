# Setup Staging dan Production di Railway

File ini menjelaskan cara membuat dua versi WebGIS:

- `staging` untuk uji coba model/UI
- `production` untuk link utama yang dibuka orang

## Konsep paling simpel

Pakai **dua service Railway** dari repo yang sama:

1. `floodgis-staging`
2. `floodgis-production`

Keduanya build dari project yang sama, tapi environment variable berbeda.

## Variabel environment

### Service staging

Isi environment variable seperti ini:

```env
HOST=0.0.0.0
PORT=8000
APP_ENV=staging
APP_ENV_LABEL=STAGING
APP_NAME=FloodGIS Jakarta Timur
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ganti-password-kuat
```

### Service production

Isi environment variable seperti ini:

```env
HOST=0.0.0.0
PORT=8000
APP_ENV=production
APP_ENV_LABEL=PRODUCTION
APP_NAME=FloodGIS Jakarta Timur
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ganti-password-kuat
```

Contoh file ada di:

- `.env.staging.example`
- `.env.production.example`

## Langkah setup di Railway

1. Push project ini ke GitHub.
2. Buat service pertama dari repo ini.
   Nama saran: `floodgis-staging`
3. Deploy sampai sukses.
4. Tambahkan environment variables staging.
5. Generate domain publik.
   Contoh: `https://floodgis-staging.up.railway.app`
6. Duplicate atau buat service kedua dari repo yang sama.
   Nama saran: `floodgis-production`
7. Tambahkan environment variables production.
8. Generate domain publik.
   Contoh: `https://floodgis-production.up.railway.app`

## Cara kerja nanti

- Kalau buka link staging:
  - homepage dan admin akan tampil banner `STAGING`
  - ini menandakan versi uji coba
- Kalau buka link production:
  - banner staging tidak muncul
  - ini versi utama
  - `admin.html` akan minta login Basic Auth

## Tes staging di lokal

- Jalankan `start_webgis_staging.bat`
- Buka `http://localhost:8010/`
- Homepage dan admin akan menampilkan banner `STAGING`

Kalau mau mode biasa di lokal, tetap pakai `start_webgis_server.bat`.

## Alur update yang aman

1. Ubah model/UI di lokal.
2. Push ke branch/repo yang dipakai deploy.
3. Cek dulu service staging.
4. Kalau sudah aman, baru update production.

## Scheduler Publik Harian

Untuk environment publik, gunakan scheduler berbasis GitHub Actions, bukan task lokal Windows:

- workflow: `.github/workflows/daily-public-refresh.yml`
- runner: `refresh_public_predictions.py`

Alur yang direkomendasikan:

1. Workflow jalan harian jam `04:00 WIB`.
2. Dataset sumber diperbarui otomatis dari Open-Meteo.
3. `data/east-jakarta-predictions.json` diregenerate.
4. Commit otomatis masuk ke branch deploy.
5. Railway staging/production yang auto-deploy akan ikut ter-refresh.

Kalau mau lebih aman:

- aktifkan workflow harian dulu di branch staging
- cek hasilnya beberapa hari
- baru izinkan branch/flow yang sama untuk production

## Jalur paling rapi

Kalau mau lebih aman lagi:

- branch `develop` -> deploy ke staging
- branch `main` -> deploy ke production

Tapi untuk tahap skripsi/demo, dua service dari repo yang sama saja sudah cukup.

## Catatan

Project ini sudah disiapkan supaya backend mengirim info environment ke frontend. Jadi penanda staging tidak di-hardcode di HTML, tapi otomatis mengikuti `APP_ENV`.
Selain itu, di mode `production` halaman `admin.html` tidak akan dibuka bebas kalau `ADMIN_USERNAME` dan `ADMIN_PASSWORD` belum diisi.
