# FloodGIS Frontend React

Frontend React ini sekarang menjadi frontend utama untuk root project dan `frontend-public`.

## Jalankan Mode Dev

```bash
npm install
npm run dev
```

## URL Dev

- Publik: `http://localhost:5173/`
- Admin: `http://localhost:5173/admin.html`

## Build Frontend Utama

```bash
npm run build:main
```

Perintah ini akan:

- build aplikasi React
- sinkronkan `index.html` dan `admin.html` root project
- sinkronkan asset build ke folder `react-assets/`
- sinkronkan paket frontend publik ke `frontend-public/`

## Catatan

- Frontend React membaca backend yang sama dengan server WebGIS utama.
- Homepage publik membaca snapshot publik aktif.
- Panel admin membaca draft live backend untuk review, override, dan publish.
- Query `?apiBaseUrl=` dan `?publicBaseUrl=` masih didukung.
