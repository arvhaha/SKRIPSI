# BAB IV - HASIL DAN PEMBAHASAN

## 4.1 Gambaran Umum

Bab ini membahas hasil pengembangan model prediksi curah hujan dan implementasinya ke dalam WebGIS risiko banjir untuk wilayah Jakarta Timur. Pembahasan dimulai dari karakteristik data dan ketidakseimbangan kelas, dilanjutkan dengan perbandingan beberapa keluarga model, evaluasi konfigurasi akhir multiclass, dan diakhiri dengan implementasi sistem WebGIS sebagai media visualisasi hasil prediksi. Fokus utama pada bab ini tidak hanya pada nilai akurasi, tetapi juga pada kemampuan model dalam mengenali kelas hujan sedang hingga lebat/ekstrem yang secara operasional lebih penting untuk mendukung kewaspadaan banjir.

Eksperimen akhir yang digunakan pada sistem operasional memanfaatkan data mulai 1 Januari 2005, panjang jendela input 3 hari (`time_steps = 3`), 26 fitur, serta arsitektur hybrid Bi-LSTM dan XGBoost dengan mekanisme selective override pada kelas menengah dan ekstrem. Konfigurasi ini dipilih karena memberikan kompromi terbaik antara performa umum model dan kemampuan mendeteksi kelas minoritas.

## 4.2 Karakteristik Data dan Ketidakseimbangan Kelas

Data yang digunakan berasal dari `Master_Data_Spasial_Jaktim_1990_sekarang.csv` dan mencakup 10 kecamatan di Jakarta Timur, yaitu Cakung, Cipayung, Ciracas, Duren Sawit, Jatinegara, Kramat Jati, Makasar, Matraman, Pasar Rebo, dan Pulo Gadung. Pada konfigurasi akhir dengan cutoff data mulai 1 Januari 2005, total sequence yang terbentuk sebanyak 78.460 sequence dengan 26 fitur masukan. Pembagian data dilakukan secara `chronological_per_district` dengan rasio 70% data latih, 15% data validasi, dan 15% data uji. Pada setiap kecamatan, data latih berakhir pada 16 Januari 2020, data validasi berakhir pada 7 April 2023, dan data uji dimulai pada 8 April 2023. Strategi ini dipilih agar evaluasi lebih merepresentasikan kondisi prediksi ke depan dan menghindari kebocoran informasi temporal.

Distribusi kelas pada data akhir menunjukkan ketidakseimbangan yang sangat kuat. Dari 78.460 sequence, kelas 0_Cerah (<5 mm) berjumlah 44.264 data, kelas 1_Ringan (5-20 mm) berjumlah 29.880 data, kelas 2_Sedang (20-50 mm) berjumlah 4.180 data, dan kelas 3_Lebat/Ekstrem (>=50 mm) hanya 166 data. Dengan kata lain, kelas ekstrem hanya sekitar 0,21% dari seluruh data. Pada set uji, kelas ekstrem juga hanya berjumlah 28 data dari total 11.780 data. Kondisi ini menjelaskan sejak awal bahwa evaluasi model tidak dapat hanya bertumpu pada akurasi, karena model yang terlalu sering menebak kelas mayoritas tetap dapat terlihat baik walaupun gagal mengenali kejadian hujan ekstrem.

Untuk mengurangi dampak ketidakseimbangan, proses penyeimbangan tidak diterapkan langsung pada data mentah, melainkan pada representasi fitur laten hasil encoder. Pada data latih, distribusi awal kelas 2 dan kelas 3 masing-masing sebesar 2.281 dan 120 data. Setelah penerapan SMOTE parsial, jumlah kelas 2 meningkat menjadi 12.933 data dan kelas 3 menjadi 3.233 data, sedangkan kelas 0 dan kelas 1 dipertahankan pada jumlah aslinya. Pendekatan ini dipilih agar model memperoleh tambahan contoh pada kelas minoritas tanpa mengganggu struktur temporal data asli secara berlebihan.

## 4.3 Perbandingan Keluarga Model

Tahap awal penelitian membandingkan beberapa pendekatan, yaitu klasifikasi biner, regresi yang dipetakan kembali ke kelas hujan, two-stage classification, dan multiclass classification langsung. Perbandingan ini penting untuk menunjukkan bahwa pemilihan model akhir tidak didasarkan pada satu metrik tunggal, melainkan pada kesesuaian pendekatan terhadap karakteristik masalah banjir dan ketidakseimbangan data.

Pada pendekatan klasifikasi biner, target dibagi menjadi dua kelas, yaitu aman (<50 mm) dan waspada (>=50 mm). Dengan threshold operasional 0,4, model menghasilkan akurasi 95,09% dan balanced accuracy 63,56%. Namun demikian, precision untuk kelas waspada hanya 1,16%, recall 31,91%, dan F1-score 2,24%. Hasil ini menunjukkan bahwa akurasi tinggi terutama disebabkan dominasi kelas aman, sedangkan performa dalam mengidentifikasi kejadian penting masih rendah. Jika threshold diturunkan hingga 0,05, recall kelas waspada dapat naik menjadi 65,96%, tetapi precision turun menjadi 0,79%, sehingga terlalu banyak false alarm untuk dipakai sebagai dasar visualisasi publik.

Pada pendekatan regresi, model memprediksi curah hujan kontinu dan hasilnya dipetakan kembali ke empat kelas curah hujan. Kandidat terbaik pada tahap pencarian model, yaitu `XGBReg_1`, sempat mencapai akurasi 70,82%, macro recall 38,02%, dan macro F1 36,89% pada evaluasi candidate. Namun pada hasil mapped-class akhir, performa turun menjadi akurasi 62,49%, macro recall 34,47%, dan macro F1 33,15%. Yang lebih penting, recall dan precision untuk kelas lebat/ekstrem sama-sama 0%. Hal ini menunjukkan bahwa pendekatan regresi cenderung lebih baik untuk mendekati nilai rata-rata curah hujan, tetapi belum memadai untuk menangkap kejadian ekstrem yang justru paling krusial dalam konteks risiko banjir.

Pada pendekatan two-stage classification, proses klasifikasi dibagi menjadi tahap pemisahan awal dan tahap klasifikasi lanjutan untuk kelas menengah hingga tinggi. Pendekatan ini sempat menunjukkan hasil validasi yang cukup menarik, dengan akurasi 57,48%, macro recall 42,86%, macro F1 36,41%, dan recall kelas ekstrem 8,43% pada kandidat terbaik. Akan tetapi, performa pada set uji menurun menjadi akurasi 48,95%, macro recall 36,46%, macro F1 32,71%, dan recall kelas ekstrem 4,35%. Penurunan ini mengindikasikan bahwa model two-stage belum menunjukkan generalisasi yang stabil terhadap data uji.

Dibandingkan ketiga pendekatan sebelumnya, multiclass classification langsung memberikan hasil yang lebih seimbang. Model akhir menghasilkan akurasi 63,04%, macro recall 39,06%, macro F1 37,08%, recall kelas lebat/ekstrem 14,29%, precision kelas lebat/ekstrem 3,81%, dan F1-score kelas lebat/ekstrem 6,02%. Walaupun nilai akurasinya tidak setinggi model biner dan tidak melampaui seluruh angka candidate regresi, pendekatan ini lebih sesuai dengan tujuan penelitian karena mampu mempertahankan representasi empat kelas hujan sekaligus tetap memberikan deteksi terbatas pada kelas ekstrem.

## 4.4 Eksplorasi Konfigurasi Multiclass

Setelah keluarga model dipersempit ke multiclass classification, eksperimen dilanjutkan pada pencarian konfigurasi jendela waktu dan cutoff tahun data. Pada eksplorasi jendela waktu awal, konfigurasi `time_steps = 7` pada subset data mulai 1 Januari 2005 menunjukkan performa yang cukup baik, yaitu akurasi 63,38%, macro recall 39,84%, macro F1 37,32%, dan recall kelas ekstrem 17,86%. Sebaliknya, konfigurasi `time_steps = 5` pada subset 2010+ hanya menghasilkan akurasi 57,64%, macro recall 35,36%, macro F1 34,75%, dan recall kelas ekstrem 5,00%. Temuan ini memperlihatkan bahwa pemilihan jendela waktu memang berpengaruh terhadap kualitas representasi pola hujan.

Pada tahap seleksi akhir, eksperimen difokuskan pada beberapa cutoff data, yaitu 2003+, 2004+, 2005+, 2006+, dan 2007+. Hasilnya menunjukkan bahwa cutoff 2004+ memberikan akurasi tertinggi, yaitu 64,76%, tetapi gagal mendeteksi kelas lebat/ekstrem dengan recall 0%. Cutoff 2003+ menghasilkan akurasi 62,16% dengan recall kelas ekstrem 3,57%. Cutoff 2006+ dan 2007+ mampu mempertahankan recall kelas ekstrem di atas 10%, tetapi precision untuk kelas ekstrem sangat rendah, masing-masing 1,43% dan 1,40%. Konfigurasi 2005+ memberikan kompromi terbaik, yaitu akurasi 63,04%, macro recall 39,06%, macro F1 37,08%, recall kelas ekstrem 14,29%, dan precision kelas ekstrem 3,81%.

Dengan demikian, konfigurasi operasional akhir ditetapkan sebagai `time_steps = 3`, `loss_mode = focal`, `training_window_start_date = 2005-01-01`, dan `ensemble_mode = gated_lstm_xgb_override`. Aturan selective override yang digunakan menetapkan threshold 0,60 untuk kelas sedang dan 0,65 untuk kelas lebat/ekstrem. Secara konseptual, LSTM digunakan sebagai prediksi dasar, sedangkan XGBoost hanya diperbolehkan melakukan override ke kelas 2 atau kelas 3 ketika probabilitas laten cukup kuat. Strategi ini dipilih untuk menekan override yang terlalu agresif sekaligus tetap memberi peluang pada model untuk menangkap sinyal ekstrem yang sulit dipelajari hanya dari keluaran dasar LSTM.

## 4.5 Evaluasi Model Final

Model multiclass final diuji pada 11.780 data uji. Hasil evaluasi menunjukkan akurasi 63,04%, macro precision 39,06%, macro recall 39,06%, dan macro F1 37,08%. Jika dilihat per kelas, performa model relatif baik pada kelas mayoritas, yaitu kelas 0_Cerah dengan precision 73,15%, recall 70,98%, dan F1-score 72,05%, serta kelas 1_Ringan dengan precision 54,54%, recall 63,37%, dan F1-score 58,62%. Pada kelas 2_Sedang, precision turun menjadi 24,73%, recall 7,62%, dan F1-score 11,66%. Sementara itu, pada kelas 3_Lebat/Ekstrem, model memperoleh precision 3,81%, recall 14,29%, dan F1-score 6,02%.

Hasil tersebut menunjukkan bahwa model sudah mampu mengenali sebagian kejadian ekstrem, tetapi performanya masih terbatas. Dari confusion matrix, hanya 4 dari 28 data kelas lebat/ekstrem yang berhasil dikenali dengan benar. Sebanyak 20 data ekstrem justru diprediksi sebagai kelas ringan dan 4 data lainnya diprediksi sebagai kelas sedang. Pola yang sama juga terlihat pada kelas sedang, di mana hanya 69 dari 905 data yang dikenali dengan benar, sementara 627 data sedang bergeser ke kelas ringan. Temuan ini mengindikasikan bahwa batas antar kelas hujan menengah hingga tinggi masih sulit dipisahkan secara tegas oleh model, terutama ketika pola temporal dan fitur cuaca antar kelas saling beririsan.

Walaupun demikian, hasil ini tetap lebih bermanfaat untuk tujuan WebGIS dibandingkan model yang sama sekali tidak mampu menangkap kelas ekstrem. Dalam konteks sistem peringatan visual, recall kelas ekstrem yang belum tinggi masih lebih berguna dibandingkan model yang hanya memberikan akurasi tinggi pada kelas mayoritas. Oleh karena itu, model akhir diposisikan sebagai alat bantu visualisasi dan prioritisasi wilayah, bukan sebagai pengganti keputusan operasional final.

## 4.6 Implementasi WebGIS

Model akhir kemudian diintegrasikan ke dalam sistem WebGIS risiko banjir Jakarta Timur. Halaman publik menampilkan ringkasan seluruh kecamatan, kontrol pemilihan wilayah, statistik singkat, peta risiko berbasis Leaflet, serta panel detail kecamatan. Setiap kecamatan divisualisasikan berdasarkan level risiko WebGIS, skor risiko, kelas hujan prediksi, dan informasi pendukung seperti kondisi drainase. Sistem juga menampilkan catatan model di halaman publik agar pengguna memahami bahwa hasil prediksi ini merupakan visualisasi pendukung dan bukan peringatan operasional final.

Halaman admin disediakan sebagai panel preview hasil model. Pada halaman ini, admin dapat melihat kecamatan prioritas, status sumber data, waktu observasi terakhir, target tanggal prediksi, model aktif, sumber curah hujan, sumber data drainase, serta detail prediksi setiap kecamatan. Admin juga dapat membuka langsung halaman peta publik untuk kecamatan tertentu melalui mekanisme deep-link, sehingga proses pemeriksaan data dari sisi internal ke tampilan publik menjadi lebih cepat dan konsisten.

Dari sisi backend, sistem mengirimkan metadata freshness seperti `latestObservationDate`, `forecastTargetDate`, `updatedAt`, dan `observationAgeDays`. Informasi ini penting agar pengguna dapat menilai apakah prediksi yang sedang dilihat berasal dari data yang masih segar atau sudah mulai usang. Jika API backend tidak tersedia, sistem dapat menggunakan fallback JSON dan menampilkan notifikasi yang jelas bahwa data yang sedang digunakan adalah data cadangan. Pendekatan ini meningkatkan robustness sistem, karena peta tetap dapat dibuka meskipun sumber utama sedang gagal dimuat.

Untuk kebutuhan deployment, halaman admin tidak dibiarkan terbuka bebas pada lingkungan produksi. Sistem mendukung proteksi berbasis Basic Auth melalui environment variable `ADMIN_USERNAME` dan `ADMIN_PASSWORD`. Dengan demikian, hasil model yang lebih rinci dan metadata backend hanya dapat diakses oleh pihak yang berwenang, sementara halaman publik tetap berfungsi sebagai kanal visualisasi informasi untuk pengguna umum.

## 4.7 Pembahasan

Secara umum, hasil penelitian menunjukkan bahwa tantangan utama bukan terletak pada menghasilkan akurasi tinggi, melainkan pada mengenali kejadian hujan sedang dan lebat/ekstrem yang jumlahnya sangat sedikit. Ketidakseimbangan data yang ekstrem membuat model cenderung belajar pola kelas mayoritas lebih cepat dibandingkan pola kelas minoritas. Fakta bahwa kelas lebat/ekstrem hanya memiliki 166 data pada keseluruhan dataset akhir dan 28 data pada set uji menjadi salah satu penyebab utama rendahnya precision dan recall pada kelas ini.

Penerapan SMOTE parsial, focal loss, dan selective override dari XGBoost terbukti membantu model untuk mulai menangkap sebagian kejadian ekstrem, walaupun peningkatannya masih terbatas. Di sisi lain, eksperimen juga memperlihatkan bahwa optimasi terhadap akurasi saja dapat menghasilkan pilihan model yang menyesatkan. Model cutoff 2004+ misalnya, memiliki akurasi tertinggi, tetapi tidak mendeteksi satu pun kejadian ekstrem. Oleh sebab itu, metrik seperti macro recall, macro F1, dan recall kelas kritis lebih relevan untuk dijadikan dasar pemilihan model pada studi ini.

Implementasi ke dalam WebGIS memperlihatkan bahwa model tidak hanya perlu baik secara numerik, tetapi juga harus dapat dijelaskan dan digunakan secara praktis. Penambahan indikator freshness, status live/fallback, catatan akurasi model, serta pemisahan halaman publik dan admin menunjukkan bahwa aspek usability dan governance sama pentingnya dengan performa model itu sendiri. Sistem yang dihasilkan belum dapat disebut sebagai sistem peringatan dini operasional penuh, tetapi sudah memadai sebagai prototipe decision-support untuk visualisasi risiko banjir berbasis prediksi curah hujan.

## 4.8 Ringkasan Bab

Berdasarkan seluruh rangkaian eksperimen, pendekatan multiclass classification langsung dengan arsitektur hybrid Bi-LSTM dan XGBoost dipilih sebagai model akhir karena memberikan keseimbangan terbaik antara performa umum dan kemampuan mendeteksi kelas ekstrem. Konfigurasi operasional yang digunakan adalah data mulai 1 Januari 2005, panjang jendela 3 hari, focal loss, dan selective override pada kelas 2 serta kelas 3. Model ini mencapai akurasi 63,04%, macro recall 39,06%, macro F1 37,08%, dan recall kelas lebat/ekstrem 14,29% pada data uji.

Hasil model tersebut kemudian berhasil diintegrasikan ke dalam WebGIS Jakarta Timur yang menyediakan visualisasi peta risiko, detail prediksi per kecamatan, indikator freshness data, fallback data cadangan, serta panel admin yang lebih aman untuk monitoring internal. Dengan demikian, penelitian ini tidak hanya menghasilkan model prediksi, tetapi juga menghasilkan prototipe sistem yang dapat digunakan untuk mendukung interpretasi risiko banjir secara spasial.

## Saran Penempatan Gambar dan Tabel

- Gambar 4.1: `01_distribusi_kelas_asli.png`
- Gambar 4.2: `02_distribusi_smote.png`
- Gambar 4.3: `03_pola_musiman.png`
- Gambar 4.4: `04_confusion_matrix_final.png`
- Gambar 4.5: `05_metrics_per_kelas.png`
- Gambar 4.6: `06_perbandingan_keluarga_model.png`
- Gambar 4.7: `07_perbandingan_window.png`
- Gambar 4.8: `08_cutoff_sweep.png`
- Gambar 4.9: `09_time_steps_2005_ce.png`
- Gambar 4.10: `10_loss_compare_ts3.png`
- Gambar 4.11: `11_training_curve.png`
- Gambar 4.12: `12_contoh_actual_vs_predicted.png`
- Gambar 4.13: `13_feature_importance_laten.png`

- Tabel 4.1: Distribusi kelas data akhir sebelum dan sesudah SMOTE.
- Tabel 4.2: Perbandingan performa pendekatan binary, regression, two-stage, dan multiclass.
- Tabel 4.3: Perbandingan konfigurasi cutoff data.
- Tabel 4.4: Hasil evaluasi per kelas untuk model multiclass final.

## Ringkasan Angka Penting

| Komponen | Nilai |
| --- | --- |
| Cutoff data final | 1 Januari 2005 |
| Jumlah sequence final | 78.460 |
| Time steps final | 3 hari |
| Jumlah fitur final | 26 |
| Train / val / test | 54.910 / 11.770 / 11.780 |
| Akurasi model final | 63,04% |
| Macro recall model final | 39,06% |
| Macro F1 model final | 37,08% |
| Recall kelas ekstrem | 14,29% |
| Precision kelas ekstrem | 3,81% |

Catatan: jika kampus kamu minta gaya penulisan tanpa tabel Markdown, isi file ini bisa langsung saya ubah ke format narasi penuh atau saya pecah lagi per subbab 4.1, 4.2, 4.3, dan seterusnya.
