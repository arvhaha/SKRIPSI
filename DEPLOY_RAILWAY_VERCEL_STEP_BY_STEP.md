# Deploy Railway + Vercel Step by Step

Panduan ini dibuat untuk arsitektur split:

- **Backend + admin + scheduler** di **Railway**
- **Frontend publik React** di **Vercel**

Tanggal acuan validasi dokumen ini: **Jumat, 24 Juli 2026**.

## Target Akhir

Hasil akhir yang kita inginkan:

- Backend publik aktif di Railway
- Frontend publik aktif di Vercel
- Frontend membaca API Railway
- Admin tetap dibuka dari backend host
- Snapshot publik, histori admin, dan histori run tetap aman di SQLite

## A. Siapkan Backend Railway Dulu

### 1. Push repo terbaru ke GitHub

Pastikan perubahan berikut sudah ikut:

- `backend_fastapi/`
- `backend_core/`
- `frontend-public/`
- `Dockerfile`
- `requirements.txt`
- `prepare_frontend_public_deploy.ps1`
- `DEPLOY_FINAL_CHECKLIST.md`

### 2. Buat project Railway

Urutan klik:

1. Buka Railway
2. Klik `New Project`
3. Pilih `Deploy from GitHub repo`
4. Pilih repo FloodGIS
5. Biarkan Railway build dari `Dockerfile`

### 3. Pasang variable backend production

Isi minimal ini di Railway Variables:

```env
HOST=0.0.0.0
PORT=8000
APP_ENV=production
APP_ENV_LABEL=PRODUCTION
APP_NAME=FloodGIS Jakarta Timur
ADMIN_USERNAME=ganti-admin-production
ADMIN_PASSWORD=ganti-password-production-yang-kuat
FLOODGIS_DB_PATH=/app/data/floodgis.db
```

Belum isi `FRONTEND_ORIGIN` dulu tidak masalah. Itu bisa diisi setelah domain Vercel jadi.

### 4. Aktifkan persistent volume Railway

Yang penting:

- mount volume ke `/app/data`
- SQLite akan hidup di `/app/data/floodgis.db`

Kalau step ini dilewatkan:

- histori admin bisa hilang saat redeploy
- histori run prediksi bisa hilang
- snapshot publik bisa jadi tidak stabil

### 5. Generate domain backend Railway

Urutan klik:

1. Buka service Railway
2. Masuk `Settings`
3. Cari `Networking`
4. Aktifkan `Public Networking`
5. Klik `Generate Domain`

Contoh hasil:

```text
https://floodgis-api-production.up.railway.app
```

Simpan domain ini. Nanti dipakai ke frontend.

### 6. Tes backend Railway

Buka:

```text
https://DOMAIN-RAILWAY/api/health
```

Yang harus dicek:

- `status = ok`
- `sqliteDbExists = true`
- `publicSnapshotExists = true` setelah publish/scheduler pertama

Lalu cek:

```text
https://DOMAIN-RAILWAY/admin.html
```

Yang benar:

- browser minta Basic Auth
- admin tidak terbuka bebas

## B. Suntik Domain Railway ke Paket Frontend

Setelah domain Railway jadi, jalanin script ini di lokal:

```powershell
.\prepare_frontend_public_deploy.ps1 `
  -ApiBaseUrl "https://DOMAIN-RAILWAY" `
  -PublicBaseUrl "https://DOMAIN-VERCEL-SEMENTARA"
```

Kalau domain Vercel final belum ada, isi sementara saja dulu:

```powershell
.\prepare_frontend_public_deploy.ps1 `
  -ApiBaseUrl "https://DOMAIN-RAILWAY" `
  -PublicBaseUrl "https://contoh-vercel-nanti-diganti.vercel.app"
```

Script ini akan mengisi:

- `frontend-public/index.html`
- `frontend-public/admin.html`

Meta yang diisi:

- `hydrogis-api-base-url`
- `hydrogis-public-base-url`

## C. Deploy Frontend Publik ke Vercel

### 1. Buat project Vercel

Urutan klik:

1. Buka Vercel
2. Klik `Add New Project`
3. Import repo GitHub yang sama
4. Saat setup project:
   - `Framework Preset`: `Other`
   - `Root Directory`: `frontend-public`
   - Build command: kosongkan
   - Output directory: kosongkan

Karena paket `frontend-public/` sudah statis, Vercel tinggal serve file yang ada.

### 2. Deploy Vercel

Setelah deploy, kamu akan dapat domain seperti:

```text
https://floodgis-jaktim.vercel.app
```

Simpan domain ini.

### 3. Kalau domain Vercel final beda dari placeholder

Jalankan ulang script lokal:

```powershell
.\prepare_frontend_public_deploy.ps1 `
  -ApiBaseUrl "https://DOMAIN-RAILWAY" `
  -PublicBaseUrl "https://DOMAIN-VERCEL-FINAL"
```

Lalu commit ulang perubahan `frontend-public/` dan push ke GitHub supaya Vercel redeploy.

## D. Finalkan Koneksi Backend ke Frontend

Sekarang balik ke Railway, isi:

```env
FRONTEND_ORIGIN=https://DOMAIN-VERCEL-FINAL
```

Kalau mau lebih fleksibel:

```env
CORS_ALLOWED_ORIGINS=https://DOMAIN-VERCEL-FINAL,https://www.DOMAIN-VERCEL-FINAL
```

Sesudah itu Railway akan redeploy.

## E. Smoke Test Final

### 1. Cek frontend publik

Buka domain Vercel:

```text
https://DOMAIN-VERCEL-FINAL
```

Yang harus lolos:

- homepage tampil
- ringkasan kecamatan tampil
- peta tampil
- data prediksi tampil

### 2. Cek health backend

Buka:

```text
https://DOMAIN-RAILWAY/api/health
```

Yang harus lolos:

- `status = ok`
- `adminApiProtected = true`
- `sqliteDbExists = true`

### 3. Cek freshness payload

Buka:

```text
https://DOMAIN-RAILWAY/api/predictions
```

Lihat `meta`:

- `freshnessStatus` idealnya `ok`
- `freshnessWarnings` idealnya kosong

Kalau tidak kosong, cek `serverDate` di `/api/health`.

## F. Admin Tetap dari Railway

Panel admin tidak perlu dipindah ke Vercel.

Admin tetap dibuka dari:

```text
https://DOMAIN-RAILWAY/admin.html
```

Ini lebih aman karena:

- Basic Auth tetap di backend
- API admin dan halaman admin tetap satu host
- tidak perlu buka akses admin ke hosting statis

## G. Kalau Mau Validasi Terhadap Jumat, 24 Juli 2026

Untuk pengecekan manual saja, bisa sementara pakai:

```env
FLOODGIS_FIXED_NOW=2026-07-24T12:00:00+07:00
```

Tapi:

- ini hanya untuk smoke test/UAT
- jangan dipakai di production final

## H. Urutan Paling Aman

Kalau mau paling minim drama, urutannya:

1. Deploy backend ke Railway
2. Pasang volume `/app/data`
3. Generate domain Railway
4. Tes `/api/health` dan `/admin.html`
5. Jalankan `prepare_frontend_public_deploy.ps1`
6. Deploy `frontend-public` ke Vercel
7. Ambil domain Vercel final
8. Isi `FRONTEND_ORIGIN` di Railway
9. Cek homepage publik
10. Cek admin backend
11. Cek `/api/predictions` freshness

## I. File Rujukan

- [DEPLOY_FINAL_CHECKLIST.md](C:/Users/Vino/Documents/SKRIPSI/DEPLOY_FINAL_CHECKLIST.md)
- [DEPLOY_RAILWAY.md](C:/Users/Vino/Documents/SKRIPSI/DEPLOY_RAILWAY.md)
- [DEPLOY_SPLIT_HYBRID.md](C:/Users/Vino/Documents/SKRIPSI/DEPLOY_SPLIT_HYBRID.md)
- [prepare_frontend_public_deploy.ps1](C:/Users/Vino/Documents/SKRIPSI/prepare_frontend_public_deploy.ps1)
