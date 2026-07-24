# Deploy Split-Hybrid FloodGIS Jaktim

Dokumen ini merangkum struktur final jika `frontend publik` dipisah dari `backend + admin + scheduler`.

## Arsitektur

```text
Frontend Publik (Vercel / Netlify)
- index.html
- admin.html
- react-assets/
        |
        | fetch
        v
Backend API + Admin + Scheduler (Railway / Render)
- webgis_backend.py
- backend_core/
- backend_core/legacy_core.py
- backend_fastapi/
- /api/predictions
- /api/geojson
- /api/admin/predictions/live
- /api/admin/publication
- /api/admin/overrides
- /api/admin/publish
- data/east-jakarta-predictions.json
- refresh_public_predictions.py
- update_openmeteo_dataset_jaktim.py
```

## File Frontend

File yang aman dipasang di hosting statis ada di folder:

- `frontend-public/`

Isi utamanya sekarang:

- `frontend-public/index.html`
- `frontend-public/admin.html`
- `frontend-public/react-assets/`

Folder ini bisa langsung dijadikan `Root Directory` di Vercel/Netlify.

## Cara update paket frontend

Jalankan dari folder `frontend-react`:

```bash
npm run build:main
```

Perintah ini akan:

1. build aplikasi React
2. sinkronkan root `index.html` dan `admin.html`
3. sinkronkan asset build ke `react-assets/`
4. sinkronkan paket deploy ke `frontend-public/`

## File Backend

File yang tetap tinggal di host backend:

- `webgis_backend.py`
- `backend_core/legacy_core.py`
- `backend_core/`
- `backend_fastapi/`
- `data/east-jakarta-predictions.json`
- `data/jkt.geojson`
- `refresh_public_predictions.py`
- `update_openmeteo_dataset_jaktim.py`

## Environment Variable Backend

Minimal untuk split-hybrid:

```env
APP_ENV=production
FRONTEND_ORIGIN=https://floodgis-jaktim.vercel.app
```

Atau kalau mau lebih dari satu origin:

```env
CORS_ALLOWED_ORIGINS=https://floodgis-jaktim.vercel.app,https://floodgis-jaktim.netlify.app
```

Untuk proteksi admin production:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ganti-password-yang-kuat
```

## Konfigurasi Frontend

Cara termudah adalah isi meta tag hasil sync di `frontend-public/index.html` dan `frontend-public/admin.html`:

```html
<meta name="hydrogis-api-base-url" content="https://floodgis-api.railway.app">
<meta name="hydrogis-public-base-url" content="https://floodgis-jaktim.vercel.app">
```

Alternatif lain yang juga didukung:

- query param `?apiBaseUrl=...`
- query param `?publicBaseUrl=...`
- `window.HYDROGIS_API_BASE_URL`
- `window.HYDROGIS_PUBLIC_BASE_URL`
- `localStorage.hydrogisApiBaseUrl`
- `localStorage.hydrogisPublicBaseUrl`

## Alur Data Publik

- Homepage publik membaca `snapshot publik aktif`
- Snapshot publik aktif berasal dari:
  - publish dari panel admin, atau
  - export scheduler backend
- Panel admin membaca `draft live backend` untuk review
- Override drainase hanya memengaruhi draft sampai admin menekan publish

Jadi alurnya:

1. backend hitung draft live
2. admin review dan override jika perlu
3. admin publish
4. homepage membaca snapshot publik hasil publish terakhir

## Urutan Deploy

1. Deploy backend dulu ke Railway/Render.
2. Catat domain backend final.
3. Isi `hydrogis-api-base-url` di frontend hasil build dengan domain backend itu.
4. Isi `hydrogis-public-base-url` di admin hasil build dengan domain frontend final.
5. Deploy folder `frontend-public` ke Vercel/Netlify.
6. Set `FRONTEND_ORIGIN` di backend sesuai domain frontend publik.
7. Uji:
   - homepage publik memuat data prediksi
   - peta tampil normal
   - admin bisa dibuka dari backend host
   - publish dari admin mengubah snapshot homepage

## Endpoint yang Dipakai Frontend

- `GET /api/predictions`
- `GET /api/geojson`
- `GET /api/health`
- `GET /api/admin/predictions/live`
- `GET /api/admin/publication`
- `POST /api/admin/overrides`
- `POST /api/admin/publish`

## Status Implementasi Saat Ini

Sudah siap di codebase:

- React menjadi frontend utama
- root `index.html` dan `admin.html` sudah serve hasil build React
- paket deploy `frontend-public` sudah berbasis hasil build React
- `webgis_backend.py` sudah jadi thin wrapper, logika inti backend dipusatkan di `backend_core/legacy_core.py`
- backend mendukung `CORS` terarah
- admin bisa diarahkan ke domain frontend publik
- status `draft live admin` dan `snapshot publik aktif` sudah dibedakan di UI
- script `sync_frontend_public.ps1` sudah disiapkan untuk refresh paket frontend dari source utama

Belum otomatis:

- inject env ke file HTML saat deploy
- pipeline deploy frontend/backend otomatis penuh

Itu bisa ditangani saat tahap publish production.
