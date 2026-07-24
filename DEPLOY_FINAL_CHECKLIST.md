# Checklist Deploy Final FloodGIS

Dokumen ini dipakai untuk final check sebelum publish backend dan frontend FloodGIS ke environment publik.

Tanggal acuan validasi dokumen ini: **Jumat, 24 Juli 2026**.

## 1. Backend Production

- [ ] `APP_ENV=production`
- [ ] `APP_ENV_LABEL=PRODUCTION`
- [ ] `APP_NAME=FloodGIS Jakarta Timur`
- [ ] `ADMIN_USERNAME` sudah diisi
- [ ] `ADMIN_PASSWORD` sudah diisi password kuat
- [ ] `FRONTEND_ORIGIN` sudah sesuai domain frontend publik
- [ ] `FLOODGIS_DB_PATH=/app/data/floodgis.db`
- [ ] `FLOODGIS_FIXED_NOW` **tidak** dipakai untuk production final

## 2. Persistent Storage

- [ ] Host backend punya persistent volume
- [ ] Volume ter-mount ke `/app/data`
- [ ] SQLite disimpan di `/app/data/floodgis.db`
- [ ] Snapshot publik tetap ditulis ke folder `data/`
- [ ] Setelah restart/redeploy, histori admin dan histori run prediksi tetap ada

## 3. Frontend Publish

- [ ] `frontend-react` sudah di-build
- [ ] `frontend-public/` sudah ter-refresh dari build terbaru
- [ ] Domain backend final sudah dimasukkan ke meta/config frontend
- [ ] Domain frontend final sudah dimasukkan ke `FRONTEND_ORIGIN`
- [ ] Halaman publik bisa buka data tanpa error CORS

## 4. Health Check Backend

Buka:

```text
/api/health
```

Pastikan:

- [ ] `status = ok`
- [ ] `serverDate` masuk akal terhadap tanggal pengecekan
- [ ] `sqliteDbExists = true` setelah backend berjalan
- [ ] `publicSnapshotExists = true` setelah publish/scheduler pertama
- [ ] `adminApiProtected = true` untuk production final

## 5. Audit Freshness

Buka:

```text
/api/predictions
```

Lalu cek `meta`:

- [ ] `updatedAt` terisi
- [ ] `serverGeneratedAt` terisi
- [ ] `serverCurrentDate` terisi
- [ ] `latestObservationDate` tidak berada di masa depan
- [ ] `forecastTargetDate` logis terhadap hari akses
- [ ] `observationAgeDays` tidak terlalu besar
- [ ] `freshnessStatus` bukan `warning` atau `stale`
- [ ] `freshnessWarnings` kosong

Catatan acuan:

- Pada **Jumat, 24 Juli 2026**, kalau backend memprediksi besok maka `forecastTargetDate` wajar bernilai **2026-07-25**.
- Pada **Jumat, 24 Juli 2026**, kalau backend menampilkan payload untuk hari yang sama maka `forecastTargetDate` wajar bernilai **2026-07-24**.
- Kalau `serverDate` atau histori run sudah menunjukkan **Sabtu, 25 Juli 2026** padahal pengecekan dilakukan pada **Jumat, 24 Juli 2026**, berarti jam server atau proses scheduler perlu diaudit.

## 6. Admin Check

- [ ] `/admin.html` meminta Basic Auth
- [ ] Draft live admin bisa dimuat
- [ ] Simpan override berhasil
- [ ] Publish ke halaman publik berhasil
- [ ] Setelah publish, override draft otomatis kosong/reset
- [ ] Riwayat aktivitas admin bertambah
- [ ] Riwayat run prediksi tampil di admin

## 7. Scheduler Check

- [ ] Scheduler harian aktif
- [ ] Scheduler memakai timezone yang benar
- [ ] Scheduler update dataset sumber dulu
- [ ] Scheduler export snapshot publik sesudah update sumber
- [ ] Histori run prediksi bertambah setelah scheduler jalan

## 8. Smoke Test Minimal

Setelah deploy, cek cepat:

- [ ] `/api/health`
- [ ] `/api/predictions`
- [ ] `/api/geojson`
- [ ] `/admin.html`
- [ ] homepage publik tampil normal
- [ ] publish dari admin mengubah snapshot publik

## 9. Kalau Mau Validasi Tanggal Secara Deterministik

Untuk testing saja, boleh set:

```env
FLOODGIS_FIXED_NOW=2026-07-24T12:00:00+07:00
```

Gunanya:

- menyamakan tanggal backend dengan tanggal acuan uji
- mempermudah audit freshness
- mempermudah UAT dan screenshot skripsi

Setelah selesai validasi:

- [ ] hapus `FLOODGIS_FIXED_NOW` dari production final
