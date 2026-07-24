# Checklist Aktivasi GitHub Actions + Railway

Checklist ini dipakai untuk mengaktifkan alur publik berikut:

1. GitHub Actions jalan setiap hari jam `04:00 WIB`
2. Workflow update `Master_Data_Spasial_Jaktim_1990_sekarang.csv`
3. Workflow regenerate `data/east-jakarta-predictions.json`
4. Workflow commit hasil terbaru ke branch deploy
5. Railway auto-redeploy dari commit terbaru

File yang dipakai:

- `.github/workflows/daily-public-refresh.yml`
- `refresh_public_predictions.py`
- `update_openmeteo_dataset_jaktim.py`
- `webgis_backend.py`
- `backend_core/legacy_core.py`
- `frontend-public/`
- `DEPLOY_RAILWAY.md`
- `STAGING_PRODUCTION_RAILWAY.md`

## 1. Preflight Repo

- Pastikan file berikut sudah ada dan ikut ke branch yang akan dideploy:
  - `model_bilstm_4class_jaktim.h5`
  - `model_xgboost_4class_jaktim.pkl`
  - `scaler_4class_jaktim.pkl`
  - `daftar_kolom_fitur_4class.pkl`
  - `Master_Data_Spasial_Jaktim_1990_sekarang.csv`
  - `data/east-jakarta-predictions.json`
  - `data/jkt.geojson`
  - `frontend-public/`
- Pastikan branch deploy sudah jelas.
  Rekomendasi paling simpel:
  - `main` untuk production
  - `develop` untuk staging
- Pastikan file workflow ada di default branch repo.
  Catatan: workflow `schedule` dan `workflow_dispatch` dipakai dari default branch.

## 2. Aktivasi GitHub Actions

- Buka repo GitHub.
- Masuk ke `Settings` -> `Actions` -> `General`.
- Di bagian `Actions permissions`, aktifkan workflow.
  Rekomendasi paling gampang:
  - pilih mode yang mengizinkan workflow menjalankan action publik GitHub
  - jangan pakai policy yang memblok `actions/checkout` dan `actions/setup-python`
- Di bagian `Workflow permissions`, pilih `Read and write permissions`.
  Ini wajib karena workflow kita melakukan `git commit` dan `git push`.
- Simpan perubahan.

Catatan:

- Opsi `Allow GitHub Actions to create and approve pull requests` tidak wajib untuk flow sekarang, karena workflow ini push langsung ke branch, bukan bikin PR.
- Kalau repo berada di organization dan setting ini tidak bisa diubah, berarti ada policy level organisasi yang harus dibuka dulu.

## 3. Cek Workflow Harian

- Buka tab `Actions` di repo.
- Cari workflow `Daily Public Prediction Refresh`.
- Pastikan workflow terlihat aktif, bukan disabled.
- Klik workflow tersebut lalu pastikan trigger ini ada:
  - `schedule`
  - `workflow_dispatch`

## 4. Pastikan Branch Deploy Cocok

- Buka file `.github/workflows/daily-public-refresh.yml`.
- Workflow saat ini akan commit ke branch tempat workflow dijalankan.
- Pastikan branch itu sama dengan branch yang dipakai Railway untuk auto-deploy.

Contoh aman:

- Railway production deploy dari `main`
- Workflow juga berjalan dari `main`

Kalau branch deploy kamu protected ketat:

- workflow push bisa gagal walaupun `contents: write` sudah aktif
- solusi paling simpel untuk tahap skripsi/demo:
  - jangan buat protection yang memblok commit dari workflow
  - atau deploy dari branch yang tidak diproteksi

## 5. Hubungkan Repo ke Railway

- Buka Railway.
- Buat project baru atau buka project yang sudah ada.
- Tambahkan service dari repo GitHub ini.
- Pastikan Railway membaca repo yang sama dengan workflow GitHub Actions.
- Pastikan `autodeploy` Railway aktif.
- Di service Railway, cek branch trigger deploy.
  Harus sama dengan branch tempat workflow commit perubahan harian.

## 6. Isi Variables di Railway

Untuk production, isi minimal:

```env
HOST=0.0.0.0
PORT=8000
APP_ENV=production
APP_ENV_LABEL=PRODUCTION
APP_NAME=FloodGIS Jakarta Timur
FRONTEND_ORIGIN=https://hydrogis-jaktim.vercel.app
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ganti-password-kuat
```

Untuk staging:

```env
HOST=0.0.0.0
PORT=8000
APP_ENV=staging
APP_ENV_LABEL=STAGING
APP_NAME=FloodGIS Jakarta Timur
FRONTEND_ORIGIN=https://hydrogis-jaktim-staging.vercel.app
ADMIN_USERNAME=admin
ADMIN_PASSWORD=ganti-password-kuat
```

Catatan:

- Railway bisa mendeteksi dan menyarankan import variabel dari file `.env` contoh di root repo.
- Kalau mau lebih rapi, shared variables bisa dipakai untuk nilai yang sama di beberapa service.
- Jangan pakai password contoh seperti `admin123`, `secret123`, atau password yang sama dengan akun lain.
- Untuk production, anggap `ADMIN_USERNAME` dan `ADMIN_PASSWORD` ini adalah pagar minimal agar `admin*.html` tidak terbuka bebas.

## 7. Checklist Proteksi Admin Production

Sebelum domain publik dibagikan, cek ini dulu:

- `APP_ENV` benar-benar bernilai `production`.
- `ADMIN_USERNAME` terisi.
- `ADMIN_PASSWORD` terisi dan bukan password lemah/default.
- Jangan publish screenshot, video, atau dokumen yang memperlihatkan credential admin.
- Kalau admin memang tidak perlu dibuka ke publik saat demo, lebih aman cukup bagikan homepage publik saja.

Perilaku yang diharapkan di production:

- Jika `ADMIN_USERNAME` dan `ADMIN_PASSWORD` belum diisi, `admin.html` harus terkunci dan mengembalikan status tidak tersedia.
- Jika credential diisi, `admin.html` harus meminta autentikasi sebelum halaman admin bisa dibuka.

Tes cepat yang wajib:

- buka `/admin.html` tanpa login
- pastikan browser meminta auth atau halaman admin tidak langsung terbuka
- coba login dengan credential yang benar
- pastikan halaman admin baru terbuka setelah autentikasi

Kalau hasilnya admin masih terbuka bebas tanpa auth, jangan lanjut publish dulu.

## 8. Aktifkan Public Domain Railway

- Buka service di Railway.
- Masuk ke `Settings`.
- Cari `Networking` -> `Public Networking`.
- Klik `Generate Domain`.
- Simpan URL publik yang dihasilkan.

Contoh endpoint yang perlu dites:

- `/`
- `/api/health`
- `/api/predictions`
- `/admin.html`

## 9. Tes Manual Workflow Sekali

- Masuk ke tab `Actions` di GitHub.
- Pilih workflow `Daily Public Prediction Refresh`.
- Klik `Run workflow`.
- Jalankan di branch deploy yang benar.

Yang harus kamu lihat:

- step install dependency sukses
- step refresh dataset sukses
- step export prediction JSON sukses
- step commit berhasil, atau menulis `Tidak ada perubahan dataset/prediksi.`

## 10. Verifikasi Setelah Workflow Jalan

- Buka commit terbaru di GitHub.
- Pastikan file yang berubah minimal:
  - `Master_Data_Spasial_Jaktim_1990_sekarang.csv`
  - `data/east-jakarta-predictions.json`
- Tunggu Railway auto-redeploy.
- Di Railway, cek deployment terbaru statusnya sukses.
- Buka URL publik Railway.

Yang perlu kamu cek di web:

- homepage tampil normal
- logo tampil normal
- peta tampil
- data freshness ikut update
- admin page production minta auth atau terkunci sesuai env

## 11. Verifikasi Jadwal Harian

- Workflow sekarang dijadwalkan dengan cron:

```yaml
0 21 * * *
```

- Itu setara dengan `04:00 WIB` pada timezone `UTC+7`.
- Besok pagi, cek apakah ada run otomatis baru di tab `Actions`.

## 12. Kalau Ada Error

Kalau gagal di GitHub Actions:

- cek `Actions permissions`
- cek `Workflow permissions = Read and write`
- cek branch deploy vs branch workflow
- cek apakah branch protection memblok `git push`
- cek apakah dependency Python sukses ter-install di runner Ubuntu

Kalau gagal di Railway:

- cek `autodeploy` aktif
- cek branch trigger benar
- cek env `ADMIN_USERNAME` dan `ADMIN_PASSWORD`
- cek build log, terutama load model TensorFlow/XGBoost
- cek file model memang ikut ke repo/image deploy

## 13. Urutan Paling Aman Buat Kamu

Kalau mau paling aman dan minim drama:

1. Push semua perubahan ke GitHub.
2. Aktifkan `Read and write permissions` di Actions.
3. Jalankan `Run workflow` manual sekali.
4. Pastikan commit update otomatis masuk.
5. Pastikan Railway auto-redeploy.
6. Baru tunggu run terjadwal besok jam `04:00 WIB`.

## Status Siap Centang

- [ ] Workflow file sudah ada di default branch
- [ ] Actions permissions sudah aman
- [ ] Workflow permissions sudah `Read and write`
- [ ] Railway service sudah connect ke repo yang benar
- [ ] Branch autodeploy Railway sudah benar
- [ ] Variables production/staging sudah diisi
- [ ] `APP_ENV=production` sudah benar untuk service publik
- [ ] `ADMIN_USERNAME` dan `ADMIN_PASSWORD` production sudah terpasang
- [ ] `/admin.html` tidak terbuka bebas tanpa auth
- [ ] Public domain Railway sudah digenerate
- [ ] Run workflow manual sudah sukses
- [ ] Commit otomatis dari workflow sudah masuk repo
- [ ] Railway auto-redeploy sudah sukses
- [ ] Website publik sudah lolos cek homepage, API, dan admin
