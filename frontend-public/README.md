# Frontend Public Package

Folder ini dipakai sebagai `Root Directory` saat deploy frontend publik ke Vercel atau Netlify.

Isinya sekarang adalah hasil build React yang sudah siap upload:

- `index.html`
- `admin.html`
- `react-assets/`

Tidak perlu lagi mengelola `script.js`, `admin.js`, atau `style.css` manual di folder ini.

## Cara update

Jalankan dari folder `frontend-react`:

```bash
npm run build:main
```

Perintah itu akan:

- build frontend React
- sinkronkan root `index.html` dan `admin.html`
- sinkronkan paket deploy ke `frontend-public/`

## Konfigurasi penting

Edit `index.html` atau `admin.html` hasil sync jika ingin mengisi meta deploy:

```html
<meta name="hydrogis-api-base-url" content="https://hydrogis-api.railway.app">
<meta name="hydrogis-public-base-url" content="https://hydrogis-frontend.vercel.app">
```

Frontend publik tetap mendukung:

- `?apiBaseUrl=...`
- `?publicBaseUrl=...`
- `localStorage.hydrogisApiBaseUrl`
- `localStorage.hydrogisPublicBaseUrl`
