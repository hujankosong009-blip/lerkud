# Dashboard SALAM MANIS — 6 November 2026

Desain baru memakai sidebar biru tua dengan aksen toska dan ungu, kartu ringkasan, tabel yang lebih terbaca, ikon SVG yang konsisten, serta font Plus Jakarta Sans dan Manrope yang disimpan di dalam aplikasi. Login, berkas pemohon, akun, notifikasi, pengelolaan dan formulir memakai gaya yang sama. Di ponsel, baris tabel Data Pemohon tampil sebagai kartu berlabel tanpa harus menggeser tabel ke samping.

## Pratinjau

Seluruh gambar di bawah memakai data sintetis, bukan data masyarakat. Simbol sementara ditampilkan ketika logo institusi belum diunggah.

- [Dashboard desktop](dashboard-desktop.png)
- [Dashboard ponsel](dashboard-mobile.png)
- [Halaman masuk](dashboard-login.png)
- [Pengaturan identitas dan logo](dashboard-branding.png)
- [Rincian permohonan](dashboard-detail.png)

## Logo transparan

1. Masuk sebagai Superadmin dan buka **Tampilan dashboard**.
2. Pilih **Logo baru · PNG transparan**, maksimal 5 MB.
3. Klik **Simpan**. Logo yang sama tampil pada sidebar, beranda dan login.

Logo sekarang disimpan sebagai PNG RGBA dengan transparansi dipertahankan. Gambar harus memiliki area transparan dan tidak seluruhnya kosong. Gambar diperiksa berdasarkan isi sebenarnya, bukan ekstensi file. Logo tampil utuh tanpa kotak latar, pemotongan, bingkai atau padding pada gambar. Pemrosesan bukti asesmen tetap terpisah dari logo.

Versi sebelumnya mengubah unggahan menjadi JPEG, sehingga logo lama perlu **diunggah ulang dari PNG asli yang transparan**. Logo lama tidak dihapus otomatis. Mengubah ekstensi JPG menjadi PNG tidak menghapus latar yang menyatu dengan gambar. Berkas logo asli dari gambar di percakapan belum tersedia di workspace; perubahan ini menyediakan tampilan dan pemrosesan yang benar untuk unggahan resmi, tanpa merekonstruksi logo institusi.

## Menerapkan di VS Code Windows

1. Hentikan server dashboard dan bot dengan Ctrl+C di terminal masing-masing.
2. Buat backup lokal:

   ```powershell
   .\.venv\Scripts\python.exe scripts\backup_local.py
   ```

3. Unduh ZIP terbaru dari GitHub dan salin **source code** ke folder proyek lama. Pertahankan `.env`, `.venv`, `db.sqlite3`, serta folder `backups`. Jangan menimpa `.env` dengan `.env.example`.
4. Periksa aplikasi:

   ```powershell
   .\.venv\Scripts\python.exe manage.py check
   ```

5. Jalankan kembali server dan bot di terminal terpisah, lalu tekan **Ctrl+F5** pada browser:

   ```powershell
   .\.venv\Scripts\python.exe manage.py runserver
   ```

   ```powershell
   .\.venv\Scripts\python.exe manage.py run_bot
   ```

Pembaruan desain ini tidak menambahkan migrasi atau dependensi Python baru. Jika source lama belum diperbarui ke alur titik akses, ikuti panduan upgrade lengkap di README. Untuk server produksi, jalankan `collectstatic` dan restart proses web sesuai cara deployment yang digunakan.

## Validasi

- Django check dan pemeriksaan migrasi: lulus, tanpa migrasi baru.
- SQLite: 75 tes ditemukan, 71 lulus dan 4 tes konkurensi PostgreSQL dilewati.
- PostgreSQL: 75 dari 75 tes lulus tanpa skip.
- Browser Chromium: login, pencarian, pembaruan tanpa klik, verifikasi, bukti privat, edit, akun, logo PNG transparan, penolakan logo berlatar penuh, dan logout lulus.
- Lebar layar yang diperiksa: 360, 390, 768, 1280 dan 1440 pixel, tanpa overflow horizontal halaman.
- PNG yang tersimpan diperiksa MIME, kanal RGBA dan piksel transparannya; latar CSS pada logo diperiksa transparan.

Pengujian tidak menggunakan token atau pesan Telegram nyata dan tidak mengubah data pengguna di komputer Windows.
