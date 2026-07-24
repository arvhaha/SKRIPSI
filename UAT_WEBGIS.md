# User Acceptance Test (UAT) WebGIS Prediksi Curah Hujan dan Risiko Banjir Jakarta Timur

Dokumen ini digunakan untuk menguji apakah sistem WebGIS yang dibangun sudah sesuai dengan kebutuhan pengguna dari sisi tampilan publik dan panel admin minimal. UAT difokuskan pada fungsi utama yang benar-benar dipakai saat sistem dijalankan, bukan pada pengujian teknis internal model.

## 1. Tujuan UAT

Tujuan UAT adalah memastikan bahwa:

- halaman publik dapat menampilkan peta, ringkasan kecamatan, dan detail wilayah dengan benar;
- data prediksi yang ditampilkan konsisten dengan payload aktif;
- informasi freshness data mudah dipahami pengguna;
- panel admin minimal dapat membantu monitoring hasil prediksi sebelum dibagikan ke publik;
- sistem tetap informatif saat backend live, fallback aktif, atau terjadi kegagalan pemuatan data.

## 2. Ruang Lingkup

Fitur yang diuji dalam UAT ini meliputi:

- homepage publik WebGIS;
- kartu ringkasan seluruh kecamatan;
- peta risiko banjir berbasis Leaflet;
- panel detail kecamatan;
- legenda level risiko;
- download CSV per kecamatan;
- status freshness data dan status sumber data;
- halaman admin minimal untuk monitoring internal.

Fitur yang tidak menjadi fokus utama UAT:

- pelatihan ulang model;
- evaluasi akurasi model secara statistik;
- scheduler harian di level sistem operasi atau GitHub Actions;
- pengujian performa server skala besar.

## 3. Aktor Pengujian

- `Pengguna publik`
  Mengakses homepage untuk melihat kondisi risiko banjir per kecamatan.
- `Admin internal`
  Mengecek hasil prediksi, freshness data, dan metadata backend sebelum data dipublikasikan.

## 4. Prasyarat Pengujian

Sebelum UAT dilakukan, pastikan:

- backend WebGIS dapat dijalankan;
- file `data/east-jakarta-predictions.json` tersedia;
- file `data/jkt.geojson` tersedia;
- browser yang dipakai dapat membuka `index.html` atau endpoint lokal WebGIS;
- data prediksi terbaru sudah berhasil di-generate.

## 5. Kriteria Penerimaan Umum

Sistem dinyatakan diterima jika:

- seluruh fungsi utama pada halaman publik berjalan tanpa error kritis;
- data kecamatan yang dipilih dari kartu atau peta langsung sinkron dengan panel detail;
- informasi freshness tampil jelas dan tidak menyesatkan;
- panel admin dapat menampilkan metadata backend dan tabel prediksi tanpa gagal render;
- bila backend gagal, sistem tetap menampilkan pesan status yang jelas;
- tidak ada komponen utama yang kosong tanpa penjelasan.

## 6. Skenario UAT Halaman Publik

| ID | Skenario Uji | Langkah Uji | Hasil yang Diharapkan | Status |
| --- | --- | --- | --- | --- |
| PUB-01 | Membuka homepage publik | Buka halaman `index.html` atau URL homepage | Header, ringkasan kecamatan, statistik, peta, panel detail, dan footer tampil normal |  |
| PUB-02 | Menampilkan ringkasan kecamatan | Tunggu halaman selesai memuat | Seluruh 10 kecamatan muncul pada kartu ringkasan |  |
| PUB-03 | Klik kartu kecamatan | Klik salah satu kartu kecamatan pada ringkasan | Peta fokus ke kecamatan yang dipilih dan panel detail terisi sesuai kecamatan tersebut |  |
| PUB-04 | Geser kartu ringkasan | Klik tombol geser kanan atau kiri pada ringkasan | Kartu dapat digeser tanpa merusak layout |  |
| PUB-05 | Klik kecamatan pada peta | Klik salah satu area kecamatan pada peta | Panel detail berubah sesuai kecamatan yang dipilih |  |
| PUB-06 | Sinkronisasi kartu dan peta | Klik wilayah pada peta setelah sebelumnya memilih dari kartu | Kartu aktif dan detail tetap sinkron dengan wilayah terbaru |  |
| PUB-07 | Menampilkan legenda risiko | Lihat legenda di area peta | Legenda menampilkan 4 level risiko: Sangat Rendah, Ringan, Sedang, dan Tinggi |  |
| PUB-08 | Menampilkan status freshness | Lihat bagian status freshness atau observasi terakhir | Tampil informasi observasi terakhir, target prediksi, waktu payload dibuat, dan usia data |  |
| PUB-09 | Menampilkan status sumber data | Lihat badge status data pada panel peta | Tampil status yang menjelaskan apakah data berasal dari backend live atau fallback |  |
| PUB-10 | Menampilkan detail kecamatan | Pilih salah satu kecamatan | Detail menampilkan tingkat risiko, curah hujan, kondisi drainase, rata-rata 3 hari, dan potensi hujan lebat/ekstrem |  |
| PUB-11 | Download CSV kecamatan | Pada panel detail, klik tombol `Download File CSV` | File CSV berhasil diunduh sesuai kecamatan yang sedang dipilih |  |
| PUB-12 | Tampilan awal detail kosong | Buka halaman baru tanpa interaksi | Area detail menampilkan instruksi singkat, bukan kosong tanpa isi |  |
| PUB-13 | Tampilan responsif dasar | Buka halaman pada ukuran layar lebih kecil | Komponen utama tetap dapat diakses dan tidak saling menumpuk secara fatal |  |
| PUB-14 | Informasi kontak footer | Scroll ke footer | Informasi kontak BMKG tampil dengan benar |  |

## 7. Skenario UAT Panel Admin

| ID | Skenario Uji | Langkah Uji | Hasil yang Diharapkan | Status |
| --- | --- | --- | --- | --- |
| ADM-01 | Membuka halaman admin | Buka `admin.html` | Halaman admin tampil normal tanpa error render |  |
| ADM-02 | Menampilkan ringkasan monitoring | Tunggu halaman admin selesai memuat | Kartu monitoring utama tampil, misalnya total kecamatan, risiko tertinggi, kecamatan siaga, dan confidence rata-rata |  |
| ADM-03 | Menampilkan tabel prediksi | Scroll ke bagian tabel prediksi | Tabel data prediksi per kecamatan tampil lengkap |  |
| ADM-04 | Membuka detail dari tabel | Klik tombol `Lihat` pada salah satu baris kecamatan | Detail baris terbuka langsung di area tabel tanpa memindahkan user secara membingungkan |  |
| ADM-05 | Menampilkan info backend | Scroll ke bagian `Info Backend` | Metadata backend tampil lengkap, seperti status sumber, observasi terakhir, target prediksi, payload dibuat, dan model aktif |  |
| ADM-06 | Kesesuaian tanggal data | Cocokkan observasi terakhir, target prediksi, dan payload dibuat | Urutan tanggal logis dan sesuai alur prediksi harian |  |
| ADM-07 | Konsistensi data dengan publik | Bandingkan satu kecamatan antara admin dan homepage | Nilai level risiko, kelas hujan, dan skor tetap konsisten |  |
| ADM-08 | Kondisi backend fallback | Uji saat backend utama tidak dipakai dan sistem memakai JSON fallback | Admin tetap menampilkan status fallback yang jelas |  |
| ADM-09 | Kondisi gagal muat | Simulasikan sumber data gagal dimuat | Tampil pesan error yang mudah dipahami, bukan halaman kosong |  |

## 8. Skenario UAT Freshness dan Data Harian

| ID | Skenario Uji | Langkah Uji | Hasil yang Diharapkan | Status |
| --- | --- | --- | --- | --- |
| DAT-01 | Kesesuaian observasi terakhir | Buka homepage atau admin setelah refresh data harian | `Observasi terakhir` menunjukkan tanggal data observasi terbaru yang benar-benar tersedia |  |
| DAT-02 | Kesesuaian target prediksi | Periksa target prediksi pada homepage atau admin | `Target prediksi` menunjukkan hari yang diprediksi, umumnya H+1 dari observasi terakhir |  |
| DAT-03 | Kesesuaian waktu payload | Lihat waktu `Payload dibuat` | Tanggal dan jam pembuatan payload tampil sesuai waktu refresh terakhir |  |
| DAT-04 | Update data setelah refresh harian | Jalankan refresh harian lalu buka ulang web | Data baru tampil tanpa harus mengubah manual isi halaman |  |

## 9. Format Hasil Uji

Gunakan keterangan berikut untuk mengisi kolom status:

- `Lulus`
- `Lulus dengan catatan`
- `Gagal`

Jika ada temuan, catat pada format berikut:

| ID Uji | Temuan | Dampak | Rekomendasi Perbaikan |
| --- | --- | --- | --- |
|  |  |  |  |

## 10. Kesimpulan UAT

Contoh narasi kesimpulan:

> Berdasarkan hasil User Acceptance Test, sistem WebGIS prediksi curah hujan dan risiko banjir Jakarta Timur telah memenuhi kebutuhan utama pengguna untuk visualisasi wilayah, penelusuran detail kecamatan, monitoring freshness data, dan review internal melalui panel admin minimal. Beberapa catatan minor yang ditemukan tidak mengganggu fungsi inti sistem, sehingga aplikasi dinilai layak digunakan sebagai prototipe visualisasi pendukung pengambilan keputusan.

Kalau ada temuan mayor, narasi bisa diubah menjadi:

> Berdasarkan hasil User Acceptance Test, sistem secara umum sudah dapat menampilkan fungsi inti, namun masih terdapat beberapa temuan yang perlu diperbaiki sebelum dinyatakan siap digunakan penuh. Temuan utama berkaitan dengan konsistensi data, kejelasan status backend, atau stabilitas tampilan pada skenario tertentu.

## 11. Lembar Persetujuan

| Peran | Nama | Tanggal | Tanda Tangan | Keterangan |
| --- | --- | --- | --- | --- |
| Penguji/Pengguna |  |  |  |  |
| Admin/Internal Reviewer |  |  |  |  |
| Peneliti/Pengembang |  |  |  |  |

## 12. Catatan Pemakaian untuk Skripsi

Kalau dokumen ini mau dimasukkan ke skripsi, bagian yang paling sering dipakai adalah:

- tujuan UAT;
- tabel skenario uji utama;
- ringkasan hasil lulus atau gagal;
- kesimpulan UAT.

Kalau mau dibuat jadi subbab di Bab 4 atau lampiran, dokumen ini sudah cukup aman dipakai sebagai draft awal.
