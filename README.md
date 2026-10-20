# SALAM MANIS

**Sadar Lapor Mandiri – Akses Mudah, Aman, Humanis.**

*Mendekatkan Akses, Menghubungkan Layanan.*

Aplikasi Django/Python untuk pelayanan melalui bot Telegram dan dashboard. PostgreSQL digunakan di produksi; SQLite tersedia untuk pengembangan lokal. Semua antarmuka menggunakan database dan aturan akses yang sama.

## Perubahan alur versi ini

**Data diri → Skrining/kendala → Self Asesmen pada website resmi → konfirmasi dan unggah screenshot → pilih dan konfirmasi titik akses → berkas dikirim ke Pelaksana lokasi tersebut → tindak lanjut.**

- Setelah kirim registrasi, bot langsung meminta kendala. Setelah kendala dikirim, bot langsung menawarkan langkah Self Asesmen.
- Tautan resmi yang diberikan pengelola, `https://selfassessment.bnn.go.id/Transactions/Assist`, diisi otomatis oleh migrasi 0005 hanya jika pengaturan tautan masih kosong. Tautan dapat diubah melalui **Superadmin → Tampilan dashboard & Self Asesmen**; pengaturan lama yang sudah terisi tidak ditimpa. Tanpa tautan, proses berhenti secara jelas pada tahap menunggu Self Asesmen; data sebelumnya tetap tersimpan.
- Website penyedia menampilkan hasilnya sendiri. SALAM MANIS menyimpan **screenshot bukti yang dikirim pemohon**, bukan menarik skor/hasil terverifikasi dari penyedia. Tidak ada integrasi API, instrumen, skor, diagnosis, atau keputusan klinis yang dibuat sendiri.
- Pemohon menyetujui penyimpanan bukti sebelum mengunggah Foto melalui chat pribadi bot. Gambar JPEG/PNG/WebP maksimal 5 MB diperiksa dan dienkode ulang untuk menghapus metadata. File palsu/SVG/resolusi berlebihan ditolak.
- Setelah bukti tersimpan, status menjadi **Menunggu Pilihan Titik Akses**. Berkas belum terlihat oleh Pelaksana dan belum ada notifikasi Pelaksana. Pemohon memilih kategori, lokasi aktif, lalu menekan **Kirim ke lokasi ini**. Setelah konfirmasi, hanya Pelaksana yang terikat ke lokasi itu menerima berkas dan notifikasi dengan tombol membuka berkas. Notifikasi tidak memuat NIK, nama, isi kendala, screenshot, atau catatan sensitif pada layar kunci. Berkas lengkap tersedia melalui bot terautorisasi dan dashboard. Pelaksana dapat menekan **Lihat bukti screenshot** di bot; gambar dikirim hanya ke chat pribadi yang masih berwenang, bukan sebagai lampiran notifikasi otomatis.
- Pelaksana memverifikasi bukti secara eksplisit. Bukti sesuai → Sedang Ditinjau; perlu perbaikan → Perlu Kelengkapan. Verifikasi berkas bukan diagnosis atau verifikasi langsung oleh penyedia asesmen.

## Dua jenis akun

**Jenis akun, bukan batas jumlah akun.** Superadmin dapat membuat beberapa akun dari kedua jenis berikut:

| Jenis | Tugas |
|---|---|
| Superadmin | Kelola akun, cakupan lokasi, undangan Telegram, direktori, ketentuan, tautan Self Asesmen, logo/keterangan dashboard, data dan arsip |
| Pelaksana | Membaca berkas dalam cakupannya, membantu pencatatan/koreksi, melihat bukti privat, memverifikasi dan memperbarui perjalanan permohonan |

Setiap akun **Pelaksana wajib terikat ke tepat satu titik akses aktif**. Tidak ada cakupan semua lokasi atau akses antrean bersama untuk Pelaksana. Hanya permohonan yang sudah dikirim dan ditujukan ke titik aksesnya yang dapat dibaca, diperbarui, atau diterima melalui notifikasi. Penugasan ganda perlu diperbaiki oleh Superadmin; akses Pelaksana diblokir sampai penugasannya menjadi satu lokasi yang valid. Flag cakupan luas dari versi lama tidak memberikan akses lintas lokasi. Superadmin memiliki akses pengelolaan lintas lokasi. Jenis akun tidak memberi kewenangan klinis otomatis.

Penghapusan permohonan **hanya oleh Superadmin**, memerlukan alasan, dan dilakukan sebagai **arsip**, bukan penghapusan permanen. Riwayat dan bukti dipertahankan; pemulihan tersedia melalui daftar Arsip. Akun dinonaktifkan melalui edit akun. Akun sendiri dan Superadmin aktif terakhir dilindungi.

## Dashboard

Halaman utama berisi **satu tabel Data Pemohon**: nama/nomor, data diri dan domisili, teks permasalahan terbaru, titik akses pilihan, status perjalanan, serta aksi ikon. Pencarian tunggal mencakup identitas, kontak, nomor, lokasi dan teks permasalahan. Tidak ada tab/tabel Skrining atau Bukti terpisah. Bukti privat, identitas lengkap, riwayat dan verifikasi dibuka melalui rincian berkas.

Tersedia ringkasan total/menunggu verifikasi/dalam penanganan/selesai tanpa menambah tabel. Aksi tambah dan arsip hanya Superadmin; lihat/edit mengikuti akses lokasi. Pencarian dilakukan setelah pemeriksaan akses. Riwayat versi kendala tetap disimpan. Pencatatan manual oleh Superadmin memerlukan akun Telegram pemohon dengan persetujuan ketentuan yang sudah ada.

**Tampilan dashboard** menyediakan logo, nama, keterangan, deskripsi, dan tautan HTTPS Self Asesmen. Unggah file logo PNG/JPG/WebP institusi pada **Tampilan dashboard → Logo baru → Simpan**. Logo yang sama tampil pada sidebar, **beranda**, dan **halaman login**. Pengaturan logo lama tetap dipakai setelah upgrade. Jika belum ada berkas logo, tampilan memakai identitas teks sementara; logo tidak direkonstruksi atau diganti dengan gambar rekaan.

**Kelola akun** menyediakan pembuatan akun, perubahan password/peran/titik akses, dan penonaktifan. Login web dan aktivasi Telegram tetap terpisah. Buat akun Pelaksana untuk setiap lokasi nyata, lalu pilih akun dan lokasi yang sama pada undangan Telegram.

## Notifikasi gratis dan cepat

Rekomendasi utama adalah **Telegram Bot API**: tidak memerlukan akun MTProto atau biaya provider pesan. Kecepatan aktual bergantung koneksi, Telegram, dan proses aplikasi tetap berjalan. Pengaturan suara/pop-up di aplikasi Telegram/perangkat pengguna tetap harus diaktifkan oleh pengguna.

**`run_bot` sekarang otomatis menjalankan pekerja notifikasi** di latar, sehingga tidak perlu lagi menjalankan `run_notifications --once` atau worker ketiga untuk penggunaan lokal. Worker memeriksa antrean setiap sekitar 1 detik, terpisah dari long polling pesan; kegagalan pengiriman tidak membatalkan penyimpanan data.

Syarat pengiriman nyata:

```dotenv
TELEGRAM_BOT_TOKEN=token_dari_BotFather
NOTIFICATION_MODE=live
NOTIFICATION_CHANNEL=bot
```

- Pemohon ditawari persetujuan notifikasi sebelum registrasi. Pilihan menolak dan menonaktifkan tetap tersedia.
- Pelaksana menekan **Setuju notifikasi & buka menu** setelah aktivasi, atau mengaktifkannya melalui **Pengaturan Notifikasi**. Tanpa persetujuan, pengiriman dicatat gagal secara jelas.
- Untuk memeriksa admin, Superadmin membuka **Kelola akun** lalu menekan ikon **Uji notifikasi Telegram** pada akun Pelaksana yang telah tertaut, atau Pelaksana membuka **Pusat notifikasi → Kirim pesan uji ke akun saya**. Uji dibatasi satu kali per menit dan dicatat di log; belum tertaut/belum menyetujui akan dijelaskan. Untuk uji end-to-end, pemohon melengkapi bukti lalu mengonfirmasi lokasi; periksa chat hanya Pelaksana lokasi itu. Pengiriman uji nyata memerlukan mode live, token valid, dan `run_bot` tetap berjalan. Buat pembaruan baru setelah mengaktifkan mode live dan persetujuan. Pesan lama yang telah ditandai **Simulasi tidak dikirim ulang**.
- Dashboard menampilkan penanda jumlah berkas menunggu verifikasi dan pemberitahuan otomatis setiap 5 detik selama halaman terbuka. Tabel aktif diperbarui tanpa mengganggu form POST yang sedang diedit. Notifikasi browser dapat diaktifkan dengan tombol izin; beberapa browser ponsel tidak mendukung notifikasi sistem tanpa service worker, tetapi penanda halaman tetap bekerja. Ini **bukan push browser ketika tab ditutup**.
- Dashboard menampilkan log antre/simulasi/gagal/terkirim, percobaan, message ID dan waktu. Status terkirim hanya dicatat setelah Telegram berhasil menerima pengiriman.

Default tetap **simulation** untuk instalasi/pengujian aman. Mengisi token lalu menjalankan `run_bot` akan membalas chat nyata, walaupun mode notifikasi masih simulasi. Gunakan bot uji dahulu. Jangan membagikan token atau traceback yang berisi token. Transport memvalidasi token, menghapus spasi tepi, dan menyamarkan error agar URL berkredensial tidak tercetak.

Untuk produksi, worker terpisah tersedia:

```bash
python manage.py run_bot --no-notifications
python manage.py run_notifications --reminders
```

Gunakan satu bot poller per token. Pada SQLite gunakan satu worker; PostgreSQL mendukung klaim antrean melalui row lock. Pengingat dideduplikasi harian, retry maksimum 5 kali dengan backoff dan waktu tunggu Telegram. Lease 5 menit memulihkan worker mati. Pengiriman jaringan **at least once**, sehingga crash setelah pengiriman diterima tetapi sebelum commit log bisa menyebabkan pesan umum berulang; tidak ada klaim exactly once.

## Menjalankan di VS Code Windows — instalasi baru

Pasang Python 3.12+ dan ekstensi Python Microsoft. Buka folder yang langsung berisi `manage.py`, lalu gunakan PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "from pathlib import Path; import secrets; p=Path('.env'); p.write_text(p.read_text().replace('replace-with-a-random-local-secret', secrets.token_hex(48)))"
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py bootstrap_manager USERNAME_ANDA
.\.venv\Scripts\python.exe manage.py runserver
```

**`.env` kini dimuat otomatis** tanpa blok PowerShell tambahan. Variabel yang diinjeksikan process manager tetap memiliki prioritas. Jika terminal lama pernah memuat environment secara manual, buka terminal baru setelah mengubah `.env` agar nilai lama tidak menimpa berkas baru. Jangan menyalin `.env.example` menimpa `.env` yang telah berisi token/kunci Anda.

Dashboard memerlukan akun hasil `createsuperuser` dan `bootstrap_manager`. Tidak ada username/password bawaan. Di terminal kedua, setelah mengisi token bot dan mode notifikasi yang diinginkan:

```powershell
.\.venv\Scripts\python.exe manage.py run_bot
```

Biarkan kedua terminal tetap berjalan. Server pengembangan tidak berjalan ketika komputer dimatikan. Untuk menutup, Ctrl+C. Endpoint `/health/` memeriksa database; `/login/` adalah halaman masuk. Tidak perlu PostgreSQL untuk mencoba lokal; `DJANGO_DEBUG=true` mengizinkan SQLite. Jangan menggunakan data pribadi nyata dalam mode debug.

## Memperbarui instalasi Windows yang sudah berisi data

**Jangan menghapus folder lama, `.env`, `.venv`, `db.sqlite3`, atau data backup.**

1. Hentikan dashboard, bot, dan worker lama dengan Ctrl+C di masing-masing terminal.
2. Unduh ZIP versi terbaru dari GitHub ke folder sementara. Salin source code baru ke folder proyek lama dan ganti berkas kode yang sama. ZIP tidak berisi `.env`, database, atau `.venv`, sehingga berkas lokal tersebut harus tetap dipertahankan.
3. Buka terminal PowerShell baru di folder proyek lama. Jalankan:

   ```powershell
   .\scripts\update_windows.ps1
   ```

   Jika kebijakan komputer melarang skrip PowerShell, gunakan perintah manual berikut tanpa mengubah kebijakan komputer.

   ```powershell
   .\.venv\Scripts\python.exe scripts\backup_local.py
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe manage.py migrate
   .\.venv\Scripts\python.exe manage.py check
   ```

4. Jalankan kembali `runserver` dan `run_bot` di dua terminal. Worker notifikasi terpisah yang lama tidak diperlukan untuk mode lokal ini.

Skrip membuat backup SQLite yang konsisten di `backups/` sebelum memasang dependensi dan bermigrasi. Backup mengandung data pribadi jika database lama berisi data pribadi: simpan secara privat dan jangan unggah ke GitHub. Untuk PostgreSQL gunakan backup/restore terkelola dan `pg_dump` sebelum menjalankan migrasi, bukan skrip backup SQLite.

Migrasi 0004 mempertahankan permohonan/profil/riwayat lama:

- SYSTEM aktif → Superadmin; COORD/LOCAL → Pelaksana. Pada pembaruan terakhir, Pelaksana hanya memakai penugasan lokasi eksplisit; flag cakupan lintas lokasi lama dinonaktifkan. Penugasan lokasi ganda digabungkan.
- Hak staff/superuser lama pada akun yang menjadi Pelaksana dicabut. Penugasan yang telah dicabut tidak dihidupkan kembali.
- Permohonan lama ditandai **versi sebelumnya**, bukan diberi screenshot atau hasil asesmen rekaan. Permohonan baru mengikuti alur tiga langkah. Kasus lama tetap dapat ditangani sesuai status lamanya.
- Kode undangan lama yang belum digunakan dicabut agar undangan baru memakai dua peran secara eksplisit. Buat ulang kode jika diperlukan.
- Migrasi data ini sengaja tidak memiliki rollback otomatis yang menebak peran lama. Pemulihan versi lama membutuhkan backup dan source versi sebelumnya.

## Menambah akun dan menghubungkan Telegram

1. Superadmin membuka **Kelola akun**, membuat username/password, memilih Superadmin/Pelaksana, serta satu titik akses untuk Pelaksana. Gunakan akun aktif yang telah diverifikasi institusi.
2. Di **Pengelolaan → Tautkan petugas ke Telegram**, pilih **akun yang sama**, lokasi, peran yang sesuai dan masa berlaku. Kode acak tampil satu kali, hanya hash disimpan, dan berlaku sekali pakai.
3. Petugas memilih Admin di bot, memasukkan kode, lalu menyetujui notifikasi. Akun web dan Telegram akan berada pada satu profil petugas. Tidak perlu memasukkan kode setiap saat.
4. Jika Telegram masih berada pada profil lama yang **belum punya login web**, undangan baru yang terikat akun/lokasi dapat menautkannya ke akun Pelaksana baru: profil lama dinonaktifkan dan pemindahan diaudit, sementara riwayatnya tetap ada. Profil yang sudah memiliki login web tidak dipindahkan otomatis; Superadmin perlu memverifikasi identitas dan menata penautannya. Jangan membagikan undangan ke orang yang tidak berwenang.
5. Perubahan akun/peran/titik akses mencabut undangan belum terpakai untuk akun tersebut. Pencabutan akun atau penugasan diperiksa ulang pada setiap tindakan dan saat pengiriman notifikasi.

## Linux/macOS dan cloud

Gunakan checkout yang ada; tugas cloud sudah terisolasi dan tidak memerlukan worktree Git tambahan.

```bash
bash scripts/install.sh
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py bootstrap_manager USERNAME_ANDA
bash scripts/start_web.sh
# Terminal kedua, hanya jika bot telah sengaja dikonfigurasi:
.venv/bin/python manage.py run_bot
```

Installer menjaga `.env` yang ada. Kunci lokal acak hanya dibuat jika belum ada `.env`.

## Produksi

Gunakan `DJANGO_DEBUG=false`, kunci acak kuat, host resmi pada `DJANGO_ALLOWED_HOSTS`, PostgreSQL `DATABASE_URL`, HTTPS, reverse proxy tepercaya, dan process manager. Default `DB_SSLMODE=verify-full`; sediakan CA tepercaya (`PGSSLROOTCERT` jika perlu). TLS tidak dimatikan untuk mengatasi masalah koneksi produksi. Tes PostgreSQL lokal hanya memakai Unix socket terisolasi tanpa TLS.

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py check --deploy
gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2 --timeout 60
```

Layani `staticfiles/` melalui reverse proxy. Gambar bukti **tidak disimpan di direktori media publik**: disimpan sebagai binary privat di database dan hanya diberikan melalui endpoint dengan login, pemeriksaan cakupan, audit akses, serta header no-store/nosniff. Logo dashboard adalah informasi publik dan dilayani terpisah. Backup database kini juga mencakup bukti gambar.

Hanya set `DJANGO_TRUST_PROXY_HTTPS=true` jika reverse proxy tepercaya menimpa header klien dan Gunicorn tidak dapat diakses langsung publik. `DJANGO_CSRF_TRUSTED_ORIGINS` dapat berisi origin HTTPS resmi. Aktifkan backup terenkripsi, retensi institusi, akses database terbatas, pengujian restore dan tata kelola data sebelum produksi. Gunicorn/layanan produksi HTTPS tidak ditujukan untuk dijalankan native di Windows; Windows lokal menggunakan runserver.

Bot API membutuhkan HTTPS ke `api.telegram.org`. Dashboard URL resmi opsional di `DASHBOARD_URL`. Kanal MTProto lama tetap opsional dan tidak dibutuhkan untuk notifikasi bot: membutuhkan akun institusi, API ID/hash/sesi melalui environment, persetujuan, kode pengaitan sekali pakai dan verifikasi ID pengirim aktual. `run_institution_linker` tidak login interaktif atau melewati pembatasan Telegram. Koneksi TCP MTProto membutuhkan jalur jaringan yang didukung dan belum dibuktikan oleh tes Bot API. Kredensial tidak boleh dimasukkan ke source, argumen CLI, audit, atau chat.

## Pengujian

```bash
.venv/bin/python manage.py test
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/test_postgres.py
.venv/bin/python scripts/test_upgrade.py
.venv/bin/python scripts/test_route_upgrade.py
CHROMIUM_PATH=/usr/bin/chromium .venv/bin/python scripts/test_browser.py
```

SQLite melewati empat tes row-lock khusus PostgreSQL. Semua data tes/screenshot sintetis; koneksi Telegram nyata ditiru. Pengujian browser mencakup pemberitahuan tanpa klik, satu tabel/search, verifikasi, upload bukti privat, edit data, logo/keterangan, akun baru, dan tampilan ponsel. Migrasi 0005 menambahkan pilihan lokasi dan menjaga berkas lama yang sudah ditugaskan. Berkas versi 0004 yang sudah memiliki bukti tetapi belum punya lokasi masuk Menunggu Pilihan Titik Akses; bukti tetap tersimpan. Migrasi tidak mengklaim lokasi lama dipilih pemohon. Lokasi direktori yang belum ada tidak diisi dengan fasilitas rekaan.

Lihat [laporan pengujian](docs/TEST_REPORT.md).

Modul utama: `models.py`/`migrations` untuk data; `services.py` untuk transaksi/alur; `access.py` untuk hak akses; `bot.py` untuk percakapan; `telegram_api.py` untuk transport; `notifications.py` untuk antrean; `uploads.py` untuk gambar; `views.py`/`forms.py`/`templates` untuk dashboard.

Direktori tujuh kategori tetap tanpa fasilitas rekaan. Referensi wilayah resmi belum tersedia; alamat manual ditandai belum terverifikasi. Ketentuan tetap berversi; persetujuan diperiksa saat pengajuan. Penjemputan, instrumen klinis internal, asesmen profesional, RAJAL/RANAP dan rujukan rinci tidak diaktifkan.
