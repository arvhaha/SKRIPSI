# Draft Drainase: Literatur, Metodologi, dan Narasi Skripsi

## 1. Perbandingan Studi dan Acuan yang Relevan

| No | Sumber | Fokus Utama | Variabel/Indikator yang Dipakai | Cara Penilaian | Relevansi untuk Project |
| --- | --- | --- | --- | --- | --- |
| 1 | Permen PUPR No. 12/PRT/M/2014 | Sistem drainase perkotaan | jaringan drainase, limpasan, genangan, operasi dan pemeliharaan | Regulasi dan pedoman umum | Cocok sebagai dasar normatif, tetapi bukan rumus skor numerik siap pakai |
| 2 | SNI 03-2406-1991 | Tata cara perencanaan umum drainase perkotaan | debit rencana, dimensi saluran, sistem jaringan | Pendekatan perencanaan teknis | Cocok sebagai dasar teknis kapasitas saluran |
| 3 | Pd T-14-2005-B | Inspeksi dan pemeliharaan drainase jalan | sedimentasi, kerusakan fisik, fungsi bangunan pelengkap, pemeliharaan | Pemeriksaan lapangan dan tindak pemeliharaan | Sangat cocok untuk indikator kondisi operasional |
| 4 | Andayani et al. (2012) | Tingkat layanan drainase perkotaan | indikator layanan, persepsi, kinerja sistem | Pembobotan indikator | Cocok sebagai inspirasi struktur indeks komposit |
| 5 | Restiani dan Sabri (2015) | Kinerja sistem drainase kawasan | kapasitas saluran dan indikator fisik | debit + skor berbobot | Paling dekat dengan kebutuhan scoring wilayah |
| 6 | Arifin (2018) | Evaluasi kinerja drainase perkotaan | kapasitas saluran, sedimentasi, dimensi | perbandingan kapasitas terhadap kebutuhan | Cocok untuk komponen kapasitas hidrolik |
| 7 | Pradana et al. (2022) | Evaluasi drainase dengan SWMM | limpasan, overflow saluran | simulasi model | Cocok bila nanti ingin level teknis lebih tinggi |
| 8 | Sari (2025) | Penilaian kinerja dan AKNOP saluran tertutup | kondisi fisik, sedimen, bangunan pelengkap, fungsi | indeks kondisi/fungsi | Cocok untuk justifikasi bahwa drainase dapat dinilai lewat indeks kondisi |

## 2. Ringkasan Temuan Penting

### 2.1 Dari acuan resmi

- Dokumen resmi Indonesia yang paling aman dijadikan dasar adalah `Permen PUPR No. 12/PRT/M/2014`, `SNI 03-2406-1991`, dan `Pd T-14-2005-B`.
- Ketiga dokumen itu memberi dasar tentang bagaimana drainase direncanakan, diinspeksi, dan dipelihara.
- Namun, ketiganya tidak memberi satu rumus nasional tunggal berbentuk `skor kualitas drainase 0-100` yang bisa langsung ditempel ke WebGIS.

### 2.2 Dari penelitian terdahulu

- Banyak penelitian menilai kinerja drainase dari dua sisi:
  1. kemampuan saluran menampung debit,
  2. kondisi fisik-operasional di lapangan.
- Jadi, praktik paling umum di skripsi/jurnal bukan sekadar menyebut drainase baik atau buruk secara subjektif, tetapi menurunkannya dari beberapa indikator.
- Pola ini konsisten pada studi Andayani et al. (2012), Restiani dan Sabri (2015), Arifin (2018), hingga studi yang lebih baru.

## 3. Metodologi yang Paling Cocok untuk Project Ini

### 3.1 Kenapa tidak pakai metode hidrolika penuh

Kalau tujuan utama project kamu adalah WebGIS prediksi risiko banjir per kecamatan, metode hidrolika penuh seperti simulasi SWMM untuk semua ruas saluran akan terlalu berat. Data yang dibutuhkan jauh lebih rinci, misalnya dimensi setiap saluran, elevasi, kekasaran, konektivitas jaringan, kapasitas inlet, dan data limpasan detail. Itu lebih cocok untuk studi evaluasi jaringan drainase teknis, bukan untuk prototipe decision-support berbasis kecamatan.

### 3.2 Metode yang direkomendasikan

Metode yang paling realistis dan tetap kuat secara akademik adalah:

- memakai acuan resmi sebagai dasar indikator,
- memakai pendekatan indeks komposit seperti penelitian terdahulu,
- lalu mengonversi hasilnya menjadi skor drainase kecamatan yang bisa dibaca model dan WebGIS.

### 3.3 Struktur indikator yang disarankan

Berikut susunan indikator yang paling masuk untuk project kamu:

| Komponen | Makna | Sumber logika |
| --- | --- | --- |
| Kapasitas saluran | apakah saluran cukup menampung aliran | SNI + studi evaluasi kapasitas |
| Sedimentasi/sampah | apakah aliran terganggu endapan atau sampah | Pd T-14-2005-B + studi lapangan |
| Kondisi fisik saluran | rusak, retak, tersumbat, atau masih baik | Pd T-14-2005-B |
| Riwayat genangan | ada atau tidak genangan berulang | Permen PUPR + data lapangan |
| Pemeliharaan | rutin atau tidak | Pd T-14-2005-B |
| Bangunan pelengkap | inlet, gorong-gorong, grill, outlet berfungsi atau tidak | Pd T-14-2005-B |

### 3.4 Usulan pembobotan

Kalau kamu mau model yang sederhana tapi tetap masuk akal, aku sarankan bobot awal seperti ini:

| Indikator | Bobot |
| --- | --- |
| Kapasitas saluran | 30% |
| Sedimentasi/sampah | 20% |
| Kondisi fisik saluran | 20% |
| Riwayat genangan | 15% |
| Pemeliharaan | 10% |
| Bangunan pelengkap | 5% |

Catatan: ini adalah **usulan sintesis metodologis** untuk penelitian kamu, bukan angka baku resmi nasional. Justru ini aman untuk skripsi selama kamu jelaskan bahwa bobot disusun berdasarkan kombinasi acuan resmi dan studi terdahulu.

### 3.5 Cara scoring yang disarankan

Setiap indikator bisa diberi skor 1 sampai 4:

- `1 = baik`
- `2 = cukup`
- `3 = kurang`
- `4 = buruk`

Lalu dihitung:

`Skor Drainase = sum(skor indikator x bobot)`

Supaya mudah dipakai di sistem, skor itu bisa dinormalisasi menjadi 0 sampai 100:

- `0-25 = Baik`
- `>25-50 = Cukup`
- `>50-75 = Buruk`
- `>75-100 = Sangat Buruk`

### 3.6 Cara menghubungkan ke WebGIS kamu

Skema paling pas buat project kamu:

- drainase tidak dijadikan target prediksi utama,
- drainase dipakai sebagai faktor penyesuaian risiko,
- curah hujan tetap menjadi penggerak utama,
- kondisi drainase memperkuat atau melemahkan skor risiko akhir.

Jadi logikanya:

- hujan sedang/lebat + drainase buruk -> risiko naik,
- hujan rendah + drainase baik -> risiko tetap rendah,
- hujan rendah + drainase sangat buruk -> risiko bisa sedikit naik, tapi tidak langsung ekstrem.

Itu juga sejalan dengan implementasi sistem kamu sekarang, karena drainase memang lebih cocok sebagai `modifier`, bukan prediktor tunggal.

## 4. Rekomendasi Praktis untuk Dataset Kamu

Supaya data drainase kamu lebih kuat, minimal tiap kecamatan nanti punya kolom seperti ini:

| Kolom | Isi |
| --- | --- |
| `kapasitas_saluran` | Baik/Cukup/Kurang/Buruk |
| `sedimentasi_sampah` | Baik/Cukup/Kurang/Buruk |
| `kondisi_fisik` | Baik/Cukup/Kurang/Buruk |
| `riwayat_genangan` | Rendah/Sedang/Tinggi |
| `pemeliharaan` | Rutin/Berkala/Jarang |
| `bangunan_pelengkap` | Berfungsi/Cukup/Bermasalah |
| `skor_drainase_total` | 0-100 |
| `kelas_drainase` | Baik/Cukup/Buruk/Sangat Buruk |

Kalau data lapangan kamu belum selengkap itu, versi minimalnya masih bisa:

- `Kondisi_Drainase_Manual`
- `Skor_Drainase_Manual`
- `Catatan_Lapangan`
- `Confidence_Drainase`

Artinya, untuk tahap skripsi/prototipe, kamu masih aman memakai semi-manual expert scoring, asalkan dijelaskan sumber penilaiannya.

## 5. Kesimpulan Metodologis

Kalau ditanya dosen, jawaban paling aman adalah:

- tidak ada satu rumus nasional tunggal yang langsung memberi skor kualitas drainase 0-100 per kecamatan,
- dasar penilaian diambil dari regulasi dan standar resmi,
- praktik penurunan skor drainase menjadi indeks komposit mengikuti pola penelitian terdahulu,
- dalam penelitian ini, drainase digunakan sebagai variabel pendukung untuk menyesuaikan skor risiko banjir berbasis prediksi curah hujan.

## 6. Draft Narasi Siap Pakai untuk Skripsi

### 6.1 Versi untuk BAB II

#### 2.x Penilaian Kondisi Drainase

Kondisi drainase merupakan salah satu faktor penting dalam pembentukan risiko banjir di wilayah perkotaan. Saluran drainase yang kapasitasnya tidak memadai, mengalami sedimentasi, tersumbat sampah, atau kurang terpelihara dapat meningkatkan peluang terjadinya genangan meskipun curah hujan yang terjadi tidak selalu berada pada kategori ekstrem. Oleh karena itu, dalam konteks penelitian ini, informasi drainase digunakan sebagai variabel pendukung untuk memperkaya interpretasi risiko banjir pada tingkat kecamatan.

Secara normatif, penilaian sistem drainase perkotaan di Indonesia mengacu pada regulasi dan standar teknis seperti Peraturan Menteri Pekerjaan Umum Nomor 12/PRT/M/2014 tentang Penyelenggaraan Sistem Drainase Perkotaan, SNI 03-2406-1991 tentang Tata Cara Perencanaan Umum Drainase Perkotaan, serta Pd T-14-2005-B tentang Pedoman Inspeksi dan Pemeliharaan Drainase Jalan. Dokumen-dokumen tersebut menjelaskan prinsip perencanaan, operasi, inspeksi, dan pemeliharaan drainase, tetapi belum memberikan satu formula tunggal berbentuk skor kualitas drainase per wilayah yang siap digunakan langsung pada sistem informasi spasial.

Dalam penelitian terdahulu, penilaian drainase umumnya dilakukan melalui pendekatan indeks atau evaluasi kinerja berbasis beberapa indikator. Andayani et al. (2012) menunjukkan bahwa tingkat layanan drainase perkotaan dapat diukur melalui indikator komposit. Restiani dan Sabri (2015) serta Arifin (2018) juga memperlihatkan bahwa evaluasi drainase lazim dilakukan dengan mempertimbangkan kapasitas saluran, kondisi fisik, sedimentasi, serta performa aliran terhadap kebutuhan debit. Dengan demikian, dapat disimpulkan bahwa pendekatan yang lazim digunakan adalah menggabungkan beberapa indikator teknis dan operasional menjadi satu ukuran kinerja drainase.

Berdasarkan dasar tersebut, penelitian ini menempatkan drainase sebagai variabel pendukung yang direpresentasikan dalam bentuk skor kondisi wilayah. Skor tersebut disusun dari informasi kondisi drainase per kecamatan, lalu digunakan untuk menyesuaikan skor risiko akhir yang sebelumnya dibentuk dari hasil prediksi kelas curah hujan. Pendekatan ini dipilih karena lebih realistis untuk skala kecamatan dan lebih sesuai dengan tujuan penelitian, yaitu membangun WebGIS visualisasi risiko banjir, bukan melakukan simulasi hidrolika rinci pada seluruh jaringan saluran.

### 6.2 Versi untuk BAB III

#### 3.x Pembentukan Variabel Drainase

Variabel drainase pada penelitian ini dibentuk sebagai variabel pendukung untuk mengoreksi atau menyesuaikan tingkat risiko banjir hasil prediksi curah hujan. Penelitian ini tidak melakukan simulasi hidrolika penuh terhadap seluruh jaringan saluran, melainkan menggunakan pendekatan indeks kondisi drainase yang lebih sederhana dan sesuai dengan skala analisis kecamatan.

Pembentukan variabel drainase didasarkan pada beberapa indikator utama, yaitu kapasitas saluran, kondisi fisik saluran, sedimentasi atau sampah, riwayat genangan, pemeliharaan, dan fungsi bangunan pelengkap. Pemilihan indikator tersebut mengacu pada regulasi dan pedoman teknis drainase perkotaan serta didukung oleh penelitian terdahulu yang menggunakan pendekatan evaluasi kinerja drainase berbasis indikator komposit.

Setiap indikator dinilai dalam skala ordinal, kemudian dikonversi menjadi skor numerik. Selanjutnya, skor tiap indikator digabungkan melalui pembobotan untuk menghasilkan skor drainase total pada tiap kecamatan. Semakin besar skor yang diperoleh, semakin buruk kondisi drainase wilayah tersebut. Skor total ini kemudian dikelompokkan ke dalam beberapa kelas, misalnya baik, cukup, buruk, dan sangat buruk.

Dalam sistem WebGIS yang dikembangkan, skor drainase tidak digunakan sebagai prediksi utama, tetapi sebagai faktor penyesuaian terhadap skor risiko banjir akhir. Dengan demikian, curah hujan hasil model tetap menjadi komponen utama, sedangkan kondisi drainase berfungsi untuk menambah konteks kerentanan wilayah. Pendekatan ini dipilih agar hasil visualisasi lebih representatif terhadap kondisi lapangan tanpa mengubah fokus utama penelitian pada prediksi curah hujan.

#### 3.x.1 Model ideal penilaian drainase

Secara ideal, kualitas drainase wilayah dapat dibentuk dari indeks komposit multi-indikator yang memadukan aspek teknis dan operasional. Indikator yang dapat digunakan meliputi kapasitas saluran, kondisi fisik saluran, sedimentasi atau sampah, riwayat genangan, pemeliharaan, fungsi bangunan pelengkap, dan kelengkapan data. Masing-masing indikator kemudian dinormalisasi ke dalam skala numerik yang sama agar dapat digabungkan menjadi satu skor total.

Secara umum, bentuk persamaan yang digunakan adalah sebagai berikut:

`Skor Drainase Total = Σ (Skor Indikator x Bobot Indikator)`

Pada pendekatan ini, bobot terbesar dapat diberikan pada kapasitas saluran karena aspek tersebut paling dekat dengan kemampuan sistem drainase dalam menampung limpasan. Contoh pembobotan yang masih rasional untuk penelitian skala kecamatan adalah kapasitas saluran 35%, kondisi fisik 20%, sedimentasi atau sampah 15%, riwayat genangan 15%, pemeliharaan 10%, dan kelengkapan data 5%. Semakin tinggi skor total yang diperoleh, semakin buruk kondisi drainase wilayah yang dinilai.

#### 3.x.2 Implementasi aktual pada penelitian

Walaupun model ideal di atas lebih lengkap secara metodologis, implementasi aktual pada penelitian ini disesuaikan dengan ketersediaan data yang benar-benar konsisten untuk seluruh kecamatan. Oleh karena itu, sistem WebGIS saat ini menggunakan pendekatan operasional yang lebih sederhana, yaitu menjadikan dimensi saluran sebagai proxy kapasitas dan menjadikan kelengkapan data sebagai confidence level.

Secara teknis, luas penampang saluran dihitung dari perkalian lebar dan tinggi saluran. Nilai tersebut kemudian dirata-ratakan pada tingkat kecamatan untuk menghasilkan proxy kapasitas wilayah. Semakin besar rata-rata luas penampang, semakin baik indikasi kapasitas drainase kecamatan tersebut. Nilai ini lalu dikonversi ke skor drainase agar dapat dipakai sebagai input pendukung pada sistem.

Selain itu, penelitian ini juga memisahkan antara kondisi drainase dan keyakinan terhadap kualitas datanya. Confidence drainase dihitung dari proporsi ruas yang memiliki dimensi lengkap dan status yang tercatat. Dengan pemisahan ini, sistem tidak hanya menampilkan hasil kondisi drainase, tetapi juga menunjukkan seberapa kuat data pendukung yang tersedia pada kecamatan tersebut.

Dalam implementasi WebGIS, hasil drainase tidak menggantikan prediksi curah hujan. Drainase hanya berfungsi sebagai faktor penyesuaian atau modifier terhadap skor risiko akhir. Dengan demikian, model hujan tetap menjadi komponen utama, sedangkan informasi drainase dipakai untuk memperkaya interpretasi risiko banjir secara spasial.

#### 3.x.3 Keterbatasan data dan implikasi metodologis

Pendekatan yang digunakan pada penelitian ini memiliki keterbatasan karena belum memasukkan seluruh indikator ideal, seperti sedimentasi lapangan, frekuensi pemeliharaan aktual, kondisi bangunan pelengkap, dan catatan genangan yang terukur secara seragam di semua kecamatan. Oleh sebab itu, skor drainase pada penelitian ini lebih tepat dipahami sebagai indeks kondisi drainase berbasis proxy kapasitas dan kualitas data, bukan sebagai audit hidrolika penuh.

Meskipun demikian, pendekatan ini tetap relevan untuk tujuan penelitian, karena fokus utama sistem adalah visualisasi pendukung keputusan pada tingkat kecamatan. Dengan pendekatan tersebut, penelitian tetap memiliki dasar metodologis yang jelas, transparan terhadap keterbatasan data, dan tetap operasional untuk diintegrasikan ke dalam WebGIS prediksi risiko banjir.

### 6.3 Versi singkat untuk penjelasan ke dosen

Pada penelitian ini, kualitas drainase tidak dihitung dari satu rumus resmi tunggal, karena regulasi nasional lebih banyak memberi prinsip perencanaan, inspeksi, dan pemeliharaan, bukan indeks numerik siap pakai per kecamatan. Oleh sebab itu, penelitian ini menggunakan pendekatan indeks komposit yang disusun dari acuan resmi dan penelitian terdahulu. Drainase kemudian diposisikan sebagai variabel pendukung yang memodifikasi tingkat risiko banjir hasil prediksi curah hujan.

## 7. Sumber Rujukan

1. Permen PUPR No. 12/PRT/M/2014: https://peraturan.bpk.go.id/Details/128245/permen-pupr-no-12prtm2014-tahun-2014
2. SNI 03-2406-1991: https://pesta.bsn.go.id/produk/detail/2774-sni03-2406-1991
3. Pd T-14-2005-B: https://binamarga.pu.go.id/index.php/nspk/detail/pedoman-inspeksi-dan-pemeliharaan-drainase-jalan?PageSpeed=noscript
4. Modul teknis drainase perkotaan PUPR/BPSDM: https://www.klop.pu.go.id/details/104
5. Andayani et al. (2012): https://ojs.uajy.ac.id/index.php/jts/article/view/8
6. Restiani dan Sabri (2015): https://journal.ubb.ac.id/fropil/article/view/1215
7. Arifin (2018): https://jurnal.ucy.ac.id/index.php/jts/article/view/839
8. Nugroho et al. (2016): https://ejournal.undip.ac.id/index.php/mkts/article/view/12508/9445
9. Pradana et al. (2022): https://journal.unpar.ac.id/index.php/jts/article/view/4539
10. Rahma et al. (2024): https://journal.ipb.ac.id/jpsl/issue/view/3532
11. Sari (2025): https://envirous.upnjatim.ac.id/index.php/envirous/article/view/352

## 8. Catatan Penting

- Bagian pembobotan pada dokumen ini adalah rekomendasi metodologis untuk project kamu.
- Kalau mau dibuat makin kuat, pembobotannya bisa kamu validasi lewat expert judgement atau AHP sederhana.
- Untuk skripsi S1, versi indeks komposit seperti ini sudah jauh lebih aman daripada sekadar memberi label drainase baik atau buruk tanpa dasar indikator.
