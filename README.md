# SALAM MANIS

**Sadar Lapor Mandiri – Akses Mudah, Aman, Humanis.**

*Mendekatkan Akses, Menghubungkan Layanan.*

Aplikasi Python/Django untuk registrasi melalui bot Telegram, penyampaian permasalahan awal, tindak lanjut petugas, dan dashboard sesuai penugasan lokasi. Bot, dashboard, dan pekerja menggunakan database serta layanan otorisasi/transaksi yang sama.

Versi pertama menyediakan seluruh alur registrasi dan Skrining naratif. Direktori tujuh kategori dimulai **tanpa fasilitas**. Self asesmen tetap **nonaktif**; tidak ada instrumen, skor, diagnosis, keputusan RAJAL/RANAP, atau rekomendasi klinis rekaan. Notifikasi dimulai dalam **simulasi**, bukan pengiriman nyata.

## Mulai pengembangan

Prasyarat: Python 3.12+, akses registry Python. Gunakan checkout yang ada; tugas cloud sudah terisolasi dan tidak memerlukan Git worktree tambahan.

```bash
cd /workspace/lerkud
./scripts/install.sh
set -a; . ./.env; set +a
.venv/bin/python manage.py test
./scripts/start_web.sh
```

Installer membuat `.venv`, memasang versi terkunci, membuat `.env` lokal dengan kunci acak **hanya jika belum ada**, menjalankan migrasi dan pemeriksaan Django. SQLite hanya diperbolehkan ketika `DJANGO_DEBUG=true`. `.env` tidak otomatis dimuat Python: gunakan perintah `set -a` di setiap terminal atau injeksikan variabel melalui pengelola proses. Jangan menggunakan data pribadi nyata dalam mode pengembangan/debug.

Dashboard tersedia pada port 8000. Login diperlukan; tidak ada akun atau kata sandi bawaan. `/health/` memeriksa akses database tanpa menampilkan data. Jalankan server pengembangan hanya di lingkungan pengembangan terkontrol.

## Membuat pengelola awal dan petugas

```bash
# Setelah memuat environment seperti di atas:
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py bootstrap_manager NAMA_USERNAME
```

Login dashboard lalu buka **Pengelolaan**. Bootstrap menautkan superuser ke peran **SYSTEM** di BNN Kota Surabaya, yang memang disebut dalam spesifikasi. Lokasi koordinator ini tidak masuk direktori tujuh kategori. Pengelola teknis tidak otomatis dapat membaca/memproses permohonan. Jika pengguna berwenang sebagai Koordinator BNN, pengelola harus menambahkan penugasan **COORD** secara terpisah.

1. Tambahkan lokasi nyata melalui Pengelolaan → Titik akses; jangan mengisi fasilitas uji pada instalasi operasional. Lengkapi kategori, alamat/wilayah, kontak, jam layanan, tautan lokasi HTTPS, dan IBM/AP jika kelurahan. Lokasi baru tidak aktif secara bawaan. Aktifkan hanya data yang disahkan.
2. Pengelola superuser membuat akun web petugas melalui administrasi Django → Users. Untuk petugas biasa, gunakan akun aktif tanpa superuser, tanpa izin pengelolaan akun. Akun dashboard dan kode aktivasi Telegram adalah mekanisme terpisah.
3. Buat **Akun petugas** dan tautkan `web_user` yang telah diverifikasi. Centang `verified`, lalu tambahkan **Penugasan petugas** dengan lokasi, peran LOCAL/COORD/SYSTEM, dan status aktif. Akun SYSTEM yang menggunakan administrasi Django juga memerlukan `is_staff`. Hanya pengelola akun yang diberi kewenangan yang boleh menjadi superuser.
4. Untuk akses Telegram, buat undangan di **Pengelolaan → Buat undangan aktivasi Telegram**. Kode acak muncul satu kali, kedaluwarsa dalam 1–168 jam (default 24), dan hanya hash yang disimpan. Berikan kode melalui kanal institusi yang aman, bukan URL dashboard.
5. Petugas memilih Admin di bot lalu memasukkan kode. Sistem membuat/menautkan akun petugas Telegram dan penugasan berdasarkan undangan. Untuk menyatukan login web dengan akun Telegram ini, buka Akun petugas, verifikasi identitas petugas, dan tautkan `web_user` ke **baris petugas Telegram yang sama**. Jangan membuat dua profil untuk orang yang sama atau menautkan akun tanpa verifikasi.
6. Akses dicabut dengan menonaktifkan penugasan atau `verified`. Pencabutan diperiksa lagi pada setiap tindakan dan saat pengiriman notifikasi. Kode belum terpakai dapat dicabut melalui Pengelolaan → Pencabutan kode.

Satu orang dapat tetap memakai menu masyarakat; perpindahan menu tidak memberikan atau menghapus peran. Admin lokal hanya melihat kasus yang ditugaskan ke lokasinya; COORD dapat melihat lintas lokasi, menetapkan lokasi/petugas, dan membuka kembali kasus dengan alasan. SYSTEM mengelola konfigurasi dan log teknis; hak itu sendiri tidak memberi akses isi kasus.

## Menjalankan bot

Isi `TELEGRAM_BOT_TOKEN` melalui environment yang aman, dan `DASHBOARD_URL` dengan alamat HTTPS operasional. Jangan menaruh token pada source, argumen perintah, screenshot, atau log.

```bash
set -a; . ./.env; set +a
.venv/bin/python manage.py run_bot
```

Perintah ini **menghubungi Telegram dan membalas pesan nyata**, termasuk ketika notifikasi masih mode simulasi. Jalankan hanya dengan bot uji/operasional yang sengaja dikonfigurasi. Gunakan satu proses polling per bot; webhook aktif perlu dikelola operator secara sengaja di Telegram, bukan dihapus otomatis aplikasi. Jaringan Bot API membutuhkan HTTPS ke `api.telegram.org`.

Percakapan layanan hanya menerima chat pribadi. `/start` menampilkan tepat Masyarakat/Admin dan tidak menghapus draft. Registrasi disimpan per field, dapat dilanjutkan/diedit per field, ringkasan NIK disamarkan, persetujuan versi aktif diperiksa ulang sebelum pengiriman. Draft Skrining juga bertahan saat berpindah menu. Identitas alamat manual diberi penanda belum terverifikasi; NIK hanya diperiksa formatnya, bukan Dukcapil. Permohonan aktif dilanjutkan, bukan dibuat ulang.

## Ketentuan, wilayah, dan layanan

- Migrasi menyertakan ketentuan awal versi 1.0. Isi versi yang sudah dibuat tidak dapat diedit melalui dashboard: buat versi baru, nonaktifkan versi lama, lalu aktifkan versi baru. Persetujuan mencatat versi/waktu; pengiriman baru memerlukan versi aktif.
- Wilayah belum memiliki referensi resmi: kota/kecamatan/kelurahan adalah input manual, tanpa klaim verifikasi. Aturan penugasan yang benar-benar diketahui dapat ditambahkan di **Aturan wilayah**; pencocokan harus sesuai ketiga field. Tanpa kecocokan, permohonan masuk antrean koordinator, tanpa menganggap domisili sebagai lokasi penanganan.
- Pengalihan lokasi/petugas hanya oleh koordinator, dengan alasan dan riwayat. Data domisili tetap terpisah.
- Status dibatasi layanan server. Skrining/kelengkapan → Menunggu Verifikasi; petugas → Ditinjau → Perlu Kelengkapan / Dalam Tindak Lanjut → Selesai. Pembatalan memerlukan alasan. Pembukaan kembali hanya COORD, dengan alasan dan tanpa permohonan aktif lain. Catatan pada status yang sama boleh dicatat sebagai pembaruan.
- **Selesai berarti proses permohonan ditutup sesuai catatan, bukan kesembuhan.**
- Progres pemohon memeriksa hubungan dengan akun Telegram. Pencarian NIK/nomor permohonan tidak pernah menjadi bukti akses. Catatan internal dan alasan internal tidak masuk progres publik.
- Konfigurasi self asesmen menyediakan versi, pertanyaan/pilihan, aturan penilaian, persetujuan, dan struktur jawaban/hasil. Tidak ada tombol aktivasi atau mesin skor pada v1. Pengaktifan instrumen yang telah ditetapkan memerlukan pengembangan lanjutan dan validasi pengelola berwenang.

## Antrean notifikasi dan pengingat

```bash
.venv/bin/python manage.py run_notifications --once
# Pekerja berkelanjutan, termasuk pengingat permohonan lama:
.venv/bin/python manage.py run_notifications --reminders
```

Default `NOTIFICATION_MODE=simulation`: antrean ditandai **simulated**, `sent_at` tetap kosong, dan tidak ada koneksi pengiriman. Pekerja juga mencatat kegagalan, percobaan (maksimal 5), waktu retry, message ID, dan waktu terkirim. Retry eksponensial menghormati waktu tunggu Telegram; kegagalan tidak membatalkan transaksi permohonan. Pengingat dibuat paling banyak sekali sehari per penerima/permohonan setelah `STALE_DAYS` (default 7). Pusat notifikasi pengelola menampilkan metadata teknis tanpa isi kasus.

Pengiriman nyata harus disengaja:

- Set `NOTIFICATION_MODE=live`, `NOTIFICATION_CHANNEL=bot` dan token bot. Pemohon/petugas membuka **Pengaturan Notifikasi → Setuju Notifikasi Bot** melalui menu progres/profil. Tanpa persetujuan, pengiriman gagal secara jelas.
- Kanal `mtproto` menggunakan akun **institusi khusus**, bukan akun pribadi petugas. Sediakan `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, dan `TELEGRAM_SESSION` (StringSession yang sudah diotorisasi melalui prosedur Telegram yang aman di luar aplikasi). Tidak ada sesi/kode OTP/password pada repo. Jalankan `run_institution_linker` dan pekerja. Aplikasi tidak melakukan login interaktif atau membuat sesi otomatis.
- Pengguna memilih **Setuju & Kaitkan Akun Institusi** di bot, lalu mengirim `/kaitkan KODE` ke akun institusi resmi yang diberikan pengelola. Kode 10 menit/sekali pakai diverifikasi terhadap ID pengirim aktual pada chat pribadi. Pekerja membutuhkan pengaitan terverifikasi, persetujuan aktif, serta dialog yang sudah terhubung; ID dari bot saja tidak cukup untuk mengirim.
- **Nonaktifkan Notifikasi** mencabut persetujuan dan kode pengaitan belum terpakai. Penugasan admin diperiksa lagi sebelum pengiriman. Notifikasi tidak berisi NIK, nama, isi Skrining, atau catatan sensitif; hanya arahan untuk membuka bot layanan.
- MTProto memerlukan akses jaringan Telegram yang sesuai (umumnya koneksi TCP ke pusat data Telegram). Allowlist HTTPS Bot API tidak membuktikan konektivitas MTProto. Deployment harus menyediakan jalur yang didukung; tidak ada mekanisme mengakali blokir/pembatasan.

Database mencatat perubahan bisnis dan antreannya dalam satu transaksi. Worker mengklaim baris dengan row lock PostgreSQL. Lease 5 menit memungkinkan pemulihan proses mati. Pengiriman jaringan bersifat **at least once**: kegagalan setelah Telegram menerima pesan tetapi sebelum commit log dapat menghasilkan pesan umum berulang. Bot menyimpan update ID untuk mencegah transaksi bisnis berulang; respons juga bisa berulang jika proses mati saat membalas. Tidak ada klaim exactly once untuk jaringan eksternal.

## Produksi PostgreSQL

Set environment produksi sebelum migrasi/startup:

- `DJANGO_DEBUG=false`, kunci acak kuat `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` untuk domain resmi.
- `DATABASE_URL` PostgreSQL dengan user database khusus. `DB_SSLMODE=verify-full` adalah default; gunakan CA tepercaya (`PGSSLROOTCERT` bila perlu). `disable` hanya digunakan oleh tes PostgreSQL lokal melalui Unix socket, bukan koneksi produksi.
- `DASHBOARD_URL=https://DOMAIN_RESMI` dan opsional `DJANGO_CSRF_TRUSTED_ORIGINS=https://DOMAIN_RESMI`.
- Reverse proxy HTTPS yang melayani `staticfiles/`, menonaktifkan log body/URL berkredensial, mengatur batas request, dan mengakses Gunicorn hanya melalui jaringan privat. Hanya jika proxy tepercaya menimpa header dari klien, set `DJANGO_TRUST_PROXY_HTTPS=true` untuk membaca `X-Forwarded-Proto`.

```bash
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check --deploy
.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2 --timeout 60
# Jalankan run_bot, run_notifications --reminders, dan linker opsional
# sebagai proses terpisah di process manager dengan environment yang sama.
```

Session autentikasi Django terpisah dari Telegram, menggunakan CSRF, password validators, cookie secure/HttpOnly di produksi, serta pembatasan percobaan login berdasarkan alamat peer langsung. Jika di belakang proxy, pertimbangkan rate limit tambahan per pengguna di lapisan proxy; jangan mempercayai header forwarded sembarang. Kode aktivasi dibatasi 5 kegagalan/15 menit per akun Telegram. Aktivitas pengelolaan, akses detail, pengiriman, penugasan, dan progres dicatat tanpa menyalin isi sensitif ke audit.

Siapkan backup terenkripsi, pemulihan teruji, kebijakan retensi data, akses database terbatas, dan tata kelola data institusi sebelum memakai data nyata. Aplikasi tidak mengklaim kepatuhan institusi sudah selesai; instalasi HTTPS/DB produksi, kredensial nyata, dan prosedur operator belum diuji dalam lingkungan pengembangan ini.

## Pengujian dan struktur

```bash
set -a; . ./.env; set +a
.venv/bin/python manage.py test --verbosity 2
.venv/bin/python manage.py makemigrations --check --dry-run
# Opsional: PostgreSQL lokal terisolasi dan browser Chromium (Linux):
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/test_postgres.py
CHROMIUM_PATH=/usr/bin/chromium .venv/bin/python scripts/test_browser.py
```

Tes tidak membutuhkan token/sesi nyata dan tidak mengirim pesan Telegram. PostgreSQL sementara serta database browser sintetis dibuat/dihapus terpisah dari database pengembangan. Skrip browser memerlukan Chromium terpasang dan menghasilkan screenshot berdata sintetis di `docs/`. Lihat [laporan pengujian](docs/TEST_REPORT.md).

| Modul | Tanggung jawab |
|---|---|
| `service/models.py`, `migrations/` | Entitas, constraint, migrasi, ketentuan awal |
| `service/services.py` | Validasi, registrasi, skrining, penugasan, transisi, kode, pengaitan |
| `service/access.py` | Pemeriksaan pemilik/peran/lokasi bersama |
| `service/bot.py`, `telegram_api.py` | Percakapan dan transport Telegram terpisah |
| `service/notifications.py` | Adapter bot/MTProto, antrean, retry, pengingat |
| `service/views.py`, `forms.py`, `templates/`, `static/` | Dashboard forest/sage/krem/earth tone yang responsif |
| `service/admin.py` | Pengelolaan konfigurasi; isi kasus melalui dashboard dengan cakupan akses |
| `service/management/commands/` | Bot, pekerja, linker, bootstrap pengelola |
| `service/tests/` | Alur, otorisasi, idempotensi, konkurensi PostgreSQL |

Belum diaktifkan: fasilitas/direktori nyata, referensi wilayah resmi, self asesmen klinis, penjemputan, asesmen profesional, RAJAL/RANAP, rujukan terperinci. Integrasi Telegram nyata membutuhkan konfigurasi/kredensial pengelola dan pengujian operasional tersendiri.
