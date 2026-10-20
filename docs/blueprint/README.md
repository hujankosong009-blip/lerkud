# Paparan Blueprint SALAM MANIS

[Buka PDF 16:9](SALAM_MANIS_Blueprint_16x9.pdf) · [Sumber HTML](SALAM_MANIS_Blueprint_16x9.html)

Paparan berbahasa Indonesia, 35 slide, dibuat 20 Oktober 2026. PDF memakai ukuran 1200 × 675 point (tepat 16:9), teks yang dapat dicari, dan bookmark untuk setiap slide. Font dan gambar telah disertakan sehingga pembaca tidak perlu memasang font tambahan. Ukuran file sekitar 2,2 MB.

## Materi

| Slide | Isi |
|---|---|
| 1–4 | Identitas, konsep, tujuan dan pembagian peran |
| 5–12 | Perjalanan masyarakat, registrasi, kendala, asesmen eksternal, bukti privat dan pilihan titik akses |
| 13–16 | Berkas yang diterima Pelaksana, status, verifikasi dan contoh percakapan bot |
| 17–20 | Dashboard satu tabel, fungsi pengelolaan, matriks akses dan penyiapan akun per lokasi |
| 21–26 | Notifikasi, uji pengiriman, arsitektur, struktur data dan privasi |
| 27–30 | Operasional VS Code, rancangan produksi, SOP dan contoh perjalanan pemohon |
| 31–34 | Bukti pengujian, roadmap, usulan KPI dan langkah pilot |
| 35 | Acuan implementasi dan penjelasan istilah |

## Mengunduh dari GitHub

Buka berkas PDF di atas, lalu pilih ikon **Download raw file**. Jika repository bersifat privat, masuk dengan akun GitHub yang memiliki akses terlebih dahulu.

## Sumber desain

Sumber HTML bersifat mandiri: CSS, font dan screenshot tertanam di dalam satu berkas. Unduh HTML untuk membuka atau mengubah teks melalui VS Code. Tata letak ditujukan untuk slide 1600 × 900 pixel dan pencetakan 16:9, bukan halaman web ponsel. PDF merupakan versi final yang telah diperiksa.

Desain menggunakan Plus Jakarta Sans, Manrope dan Space Grotesk, warna biru tua, toska serta ungu, diagram vektor dan screenshot dashboard aktual dengan data sintetis. Lisensi font disertakan dalam [FONT_LICENSES.txt](FONT_LICENSES.txt). Logo asli institusi belum tersedia sebagai berkas di workspace; paparan memakai identitas tipografi SALAM MANIS.

## Dasar dan batas materi

Materi dicocokkan dengan kode pada commit `b5a0fe4`, README, aturan akses, alur bot, antrean notifikasi dan [laporan pengujian](../TEST_REPORT.md). Paparan membedakan fungsi yang tersedia, hasil uji sintetis dan rekomendasi pengembangan. Website BNN belum tersambung melalui API/webhook; bukti asesmen berupa screenshot yang dikirim pemohon. Pengiriman Telegram nyata dan popup perangkat tetap perlu diuji pada instalasi operasional. KPI, target respons dan SOP merupakan usulan untuk disepakati pengelola, bukan hasil layanan yang telah diukur.

Pembuatan paparan ini tidak mengubah source aplikasi, konfigurasi, database, akun, token, maupun proses pengiriman pesan.
