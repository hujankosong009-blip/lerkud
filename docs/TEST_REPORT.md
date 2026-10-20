# Laporan pengujian — SALAM MANIS

Pembaruan alur 20 Oktober 2026 (Asia/Jakarta). Python 3.12.14, Django 5.2.18, PostgreSQL lokal sementara 16.2 dan Chromium. Semua pemohon, lokasi, isi kendala, password tes dan gambar bukti dalam pengujian/screenshot adalah sintetis. Tidak ada pesan Telegram nyata dikirim.

## Hasil validasi

| Pemeriksaan | Hasil |
|---|---|
| Suite SQLite | 61 tes ditemukan: 58 lulus, 3 konkurensi PostgreSQL dilewati |
| Suite PostgreSQL sementara | 61/61 lulus, tanpa skip; migrasi dan teardown selesai, exit 0 |
| Upgrade database versi 0003 → 0004 | Lulus: peran lama dipetakan, cakupan dipertahankan, penugasan digabungkan, hak superuser Pelaksana dicabut, akun yang dicabut tidak hidup kembali, permohonan lama tetap ada, undangan lama dicabut |
| Browser desktop 1440 × 1100 / ponsel 390 × 844 | Lulus: tanpa overflow horizontal halaman dan tanpa error JavaScript |
| Pembaruan dashboard tanpa klik | Lulus: perubahan database dari proses lain menghasilkan pemberitahuan dan pembaruan tabel |
| Tiga tabel dan pencarian | Lulus: Data pribadi, Skrining/kendala, Bukti Self Asesmen |
| Alur browser | Lulus: login, verifikasi, upload screenshot, edit data, ubah keterangan/logo, tambah akun Pelaksana dan logout |
| `makemigrations --check --dry-run` | Tidak ada perubahan model tanpa migrasi |
| `manage.py check` | Tidak ada masalah |
| `collectstatic --noinput` | Berkas statis baru berhasil dikumpulkan |
| Backup SQLite sebelum update | Helper berhasil membuat backup konsisten tanpa mengubah database sumber |

## Cakupan penting suite

- `/start` hanya dua akses utama, seluruh menu masyarakat, kelanjutan draft dan tidak ada penghapusan data oleh perpindahan menu.
- Persetujuan ketentuan versi aktif, format NIK/telepon/RT/RW, alamat manual belum terverifikasi, ringkasan NIK tersamarkan, koreksi per field, pembatalan draft dan pesan registrasi yang diminta.
- Idempotensi update Telegram, constraint satu permohonan aktif, dua submit registrasi bersamaan, dan satu pemenang aktivasi bersamaan.
- Setelah registrasi langsung masuk kendala; setelah kendala masuk tautan eksternal; URL belum diisi memblokir langkah tersebut secara jelas tanpa membuat instrumen/skor/link rekaan.
- Persetujuan notifikasi eksplisit: dapat ditolak, diaktifkan atau dicabut. Persetujuan penyimpanan bukti sebelum unggah.
- Screenshot hanya diterima setelah data diri/kendala dan tautan tersedia. Kepemilikan diperiksa di server. Gambar palsu, SVG, kosong dan terlalu besar ditolak; gambar valid dienkode ulang.
- Bukti bersifat privat: login/cakupan/keaktifan akun diperiksa pada endpoint gambar dan saat mengirim gambar ke chat pribadi bot. Tidak ada direktori media publik. Akses dicabut mencegah pengiriman meskipun respons bot sebelumnya sudah tersimpan.
- Duplikasi screenshot tidak membuat versi ganda. Screenshot yang ditolak tidak dapat dikirim ulang identik lalu diklaim lengkap. Perbaikan menyimpan riwayat versi.
- Pelaksana menerima notifikasi berkas lengkap setelah bukti masuk, bukan saat registrasi/kendala belum lengkap. Isi notifikasi umum dan memiliki tombol akses; tidak memuat identitas/screenshot/kendala.
- Simulasi tidak mengirim transport nyata dan `sent_at` tetap kosong; kegagalan tidak menghapus permohonan. Retry mengikuti waktu tunggu Telegram. Persetujuan/cakupan diperiksa ulang saat pengiriman.
- `run_bot` memulai worker notifikasi otomatis secara default; worker terpisah tetap opsional.
- Hanya dua jenis akun, kewenangan pengelolaan ditolak bagi Pelaksana, pembatasan lokasi diterapkan sebelum pencarian, serta penonaktifan login web turut mencabut akses bot.
- Verifikasi bukti eksplisit diperlukan sebelum kasus baru masuk Ditinjau; transisi tidak sah dan penyimpanan status lama ditolak. Catatan internal tidak masuk progres pemohon. Pembukaan kembali dibatasi Superadmin.
- CRUD data: pencatatan manual memerlukan persetujuan asli yang sudah ada, edit kendala berversi, penghapusan ke arsip memerlukan alasan, arsip tetap menyimpan bukti/riwayat, dan pemulihan tidak membuka status secara diam-diam.
- Kelola akun: pembuatan, perubahan peran, penonaktifan, perlindungan akun sendiri dan Superadmin terakhir; dua demosi bersamaan tetap mempertahankan satu Superadmin.
- Logo/keterangan dan tautan resmi HTTPS dapat diubah; Pelaksana tidak dapat mengubahnya melalui POST palsu.
- URL tombol Telegram, batas byte callback, sanitasi error token, pembatasan login/aktivasi, CSRF, aturan wilayah, pengingat idempoten, dan pengaitan penerima MTProto berbasis pengirim yang benar.
- Penyimpanan waktu aware/UTC dan konversi tampilan Asia/Jakarta.

## Screenshot hasil browser

- [Dashboard desktop](dashboard-desktop.png)
- [Dashboard ponsel](dashboard-mobile.png)

Database browser sintetis terpisah dan dihapus setelah tes. Tidak ada akun atau fasilitas contoh yang ditambahkan ke database pengembangan.

## Batas bukti

- Pengiriman Bot API/MTProto nyata tidak dijalankan; semua transport Telegram ditiru. Pengiriman operasional membutuhkan token benar, mode live, persetujuan, koneksi Telegram dan bot/worker yang tetap berjalan.
- Notifikasi sistem browser bergantung dukungan/izin browser dan halaman yang masih terbuka. Ini bukan implementasi web push ketika tab ditutup. Pemberitahuan/penanda pada halaman diuji langsung.
- Tautan BOSS BNN nyata belum diberikan. Bukti yang disimpan adalah screenshot kiriman pemohon/petugas, bukan hasil yang diambil/terverifikasi otomatis dari penyedia.
- Referensi wilayah/fasilitas resmi belum diisi. Tidak ada instrumen klinis, skor, diagnosis atau keputusan RAJAL/RANAP yang diaktifkan.
- Pengujian berlangsung di Linux. Skrip PowerShell pembaruan disediakan untuk Windows, tetapi belum dieksekusi pada Windows pengguna. Helper backup Python dan alur aplikasi yang dipakai skrip telah dijalankan.
- PostgreSQL produksi, reverse proxy HTTPS, sertifikat produksi, deployment 24 jam, publikasi environment dan pemulihan tugas cloud baru tidak diklaim telah diverifikasi.

Dokumen ini menggantikan laporan versi awal; perubahan perilaku baru mengikuti permintaan dua peran serta bukti self asesmen, sementara data versi lama dijaga melalui migrasi.
