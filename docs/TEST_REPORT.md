# Laporan pengujian SALAM MANIS — pilihan titik akses

Dijalankan 20 Oktober 2026 (Asia/Jakarta), Python 3.12.14, Django 5.2.18, PostgreSQL sementara 16.2 dan Chromium. Seluruh pemohon, lokasi, kendala, gambar dan akun tes adalah sintetis. Transport Telegram ditiru; tidak ada pesan nyata dikirim dari lingkungan pengujian.

## Hasil

| Pemeriksaan | Hasil |
|---|---|
| Suite PostgreSQL | **73/73 lulus**, tanpa skip; migrasi dan teardown selesai, exit 0 |
| Suite SQLite | **69 lulus, 4 dilewati** (konkurensi khusus PostgreSQL), 73 ditemukan |
| Upgrade dari 0003 | Lulus: dua peran, cakupan lokasi eksplisit, hak Pelaksana dibatasi, penugasan/riwayat lama dipertahankan |
| Upgrade dari 0004 | Lulus: berkas yang sudah ditugaskan tetap terkirim; bukti tanpa lokasi tetap ada dan menunggu konfirmasi pemohon; flag akses semua lokasi tidak berlaku |
| Browser desktop/ponsel | Lulus pada 1440 × 1100 dan 390 × 844, tanpa error JavaScript atau overflow horizontal halaman |
| Dashboard satu tabel | Lulus: data diri + teks permasalahan + titik akses + status, pencarian tunggal, detail, edit, upload bukti, verifikasi |
| Logo dan tampilan | Lulus: file logo unggahan yang sama muncul pada beranda dan login; perubahan keterangan, logo dan akun melalui form berjalan |
| Pembaruan tanpa klik | Lulus: perubahan database dari proses lain menghasilkan pemberitahuan dan pembaruan tabel |
| Pemeriksaan model | `makemigrations --check --dry-run`: tidak ada perubahan tanpa migrasi |
| Pemeriksaan Django | `manage.py check`: tidak ada masalah |

## Bukti isolasi titik akses dan notifikasi

- Sebelum konfirmasi lokasi, status **Menunggu Pilihan Titik Akses**. Bukti sudah tersimpan, tetapi Pelaksana A maupun B tidak dapat melihat permohonan dan tidak memperoleh notifikasi berkas baru.
- Setelah pemohon memilih B dan menekan **Kirim ke lokasi ini**, status berubah ke Menunggu Verifikasi. Data muncul pada akun B. Transport Bot API tiruan menerima pesan ke chat Pelaksana B, bukan A, dengan tombol membuka berkas.
- Flag `all_locations=True` dari versi lama tidak membolehkan A melihat kasus B. Pelaksana yang belum memiliki tepat satu lokasi aktif memerlukan perbaikan konfigurasi, bukan diberi akses antrean bersama.
- Pencarian, detail, screenshot privat, pembaruan status, dan akses melalui callback bot memeriksa cakupan server. Mengetik nomor/URL/callback kasus lokasi lain tidak memberikan akses.
- Pengiriman ke lokasi yang sama berulang bersifat idempoten. Upaya mengganti ke lokasi lain setelah terkirim ditolak bagi pemohon. Dua konfirmasi lokasi berbeda bersamaan hanya menghasilkan satu tujuan, satu riwayat penugasan dan satu peristiwa berkas baru.
- Pilihan lokasi yang belum aktif, kategori koordinator, dan pemilihan sebelum bukti lengkap ditolak. Jika kategori belum berisi lokasi aktif, bukti tetap tersimpan dan bot menjelaskan kondisinya.
- Jika Superadmin memindahkan penugasan, penerima lama tidak menerima notifikasi baru, dan antrean lama diperiksa ulang sebelum pengiriman. Riwayat publik menyebut lokasi penanganan yang benar; lokasi hasil pemindahan tidak diklaim sebagai pilihan pemohon.
- Tombol **Uji notifikasi Telegram** dapat mengantrekan pesan uji ke akun yang tepat. Pengujian memastikan status sent hanya setelah respons sukses transport, persetujuan wajib, akun harus tertaut/aktif, cooldown satu menit, serta Pelaksana tidak dapat menguji akun orang lain.

## Cakupan lain yang dipertahankan

Registrasi bertahap/draft/edit, persetujuan ketentuan aktif, validasi identitas, penyamaran NIK, pencegahan duplikasi pengiriman, batas kepemilikan, skrining berversi, tautan eksternal tanpa skor rekaan, persetujuan unggah, validasi gambar dan metadata, screenshot privat, verifikasi eksplisit, transisi sah, catatan internal terpisah dari progres publik, arsip/pemulihan, CSRF, rate limit, sanitasi token, retry/flood wait, simulasi, worker bawaan bot, pengingat idempoten, waktu Asia/Jakarta, kelola akun dan perlindungan Superadmin terakhir.

Tautan aktivasi akun yang terikat lokasi diperiksa terhadap peran/lokasi akun yang masih berlaku. Profil Telegram lama tanpa login web dapat ditautkan ke akun lokasi melalui undangan baru yang sah; profil lama dicabut dan riwayat dipertahankan. Target yang tidak valid tidak mengubah profil lama.

## Screenshot

- [Dashboard desktop](dashboard-desktop.png)
- [Dashboard ponsel](dashboard-mobile.png)

Screenshot berasal dari database sementara dan memakai identitas teks bawaan. Logo unggahan diuji dengan gambar sintetis, bukan dengan mengarang ulang logo institusi. Untuk memakai logo asli, unggah berkasnya di Tampilan dashboard; logo tersebut tampil pada sidebar, beranda, dan halaman login. Gambar logo yang terlihat di percakapan belum tersedia sebagai berkas asli di workspace saat validasi.

## Batas pengujian

- **Belum ada uji pengiriman Telegram nyata di lingkungan ini.** Hasil tiruan membuktikan pemilihan penerima dan pemrosesan antrean, bukan popup pada ponsel pengguna. Gunakan tombol uji pada instalasi operasional dengan token benar, mode live, bot/worker berjalan, akun tertaut, persetujuan, dan izin notifikasi Telegram pada perangkat.
- Tidak ada fasilitas, kontak, instrumen, skor atau hasil klinis rekaan. Pemohon harus memilih titik akses yang benar-benar diaktifkan Superadmin dan memiliki akun Pelaksana yang disiapkan pengelola.
- Situs BNN tidak diintegrasikan melalui webhook/API. Screenshot adalah bukti kiriman, bukan hasil terverifikasi dari penyedia.
- Notifikasi browser diuji untuk halaman yang terbuka, bukan web push setelah tab ditutup.
- Skrip PowerShell disediakan untuk Windows tetapi pengujian otomatis berjalan di Linux. Data pengguna Windows tidak diubah dari lingkungan ini; jalankan backup dan migrasi di komputer pengguna setelah menyalin source baru.
- HTTPS/DB produksi, sesi MTProto nyata, publikasi cloud dan pemulihan snapshot baru belum diverifikasi.
