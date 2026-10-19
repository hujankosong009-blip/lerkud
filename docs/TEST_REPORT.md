# Laporan pengujian SALAM MANIS

Dijalankan 19 Oktober 2026 (Asia/Jakarta), Python 3.12.14, Django 5.2.18. Semua identitas, lokasi, dan uraian dalam tes/screenshot adalah sintetis. Tidak ada pesan Telegram nyata dikirim.

## Hasil akhir

| Pemeriksaan | Hasil |
|---|---|
| `manage.py test` · SQLite | 42 ditemukan: **40 lulus**, **2 dilewati** karena membutuhkan row lock PostgreSQL |
| `scripts/test_postgres.py` · PostgreSQL 16.2 sementara | **42/42 lulus**, tidak ada dilewati; migrasi dan teardown selesai, exit 0 |
| `scripts/test_browser.py` · Chromium | **Lulus**: login, ringkasan, daftar, detail, simpan progres, logout ponsel, tanpa error JavaScript |
| Tata letak browser | **Lulus** pada 1440 × 1100 dan 390 × 844; tidak ada overflow horizontal halaman |
| `makemigrations --check --dry-run` | Tidak ada perubahan model tanpa migrasi |
| `manage.py check` | Tidak ada masalah |
| `manage.py check --deploy` | Tidak ada masalah dengan pengaturan produksi sintetis; bukan tes koneksi DB/HTTPS produksi |
| `collectstatic --noinput` | 128 berkas statis dikumpulkan |
| Installer dua kali | Lulus; instalasi/migrasi berulang tidak mengubah `.env` yang sudah ada |
| Startup aktual pengembangan | `/health/` mengembalikan `ok`; `/login/` memuat form dengan CSRF |
| Pekerja simulasi | Perintah satu siklus dan proses berkelanjutan dapat dijalankan; tanpa pesan nyata |

## Cakupan 18 persyaratan wajib

| Persyaratan | Bukti tes |
|---|---|
| Dua pilihan `/start`; draft tidak dihapus | `test_start_two_options_and_draft_survives`, `test_private_chat_only` |
| Seluruh tujuh menu masyarakat terlihat | `test_start_two_options_and_draft_survives` |
| Registrasi simpan/lanjut/edit | `test_registration_resume_edit_mask_and_exact_success` |
| Validasi, persetujuan aktif, alamat manual | `test_each_field_validation_and_manual_address`, `test_consent_required_and_terms_version_changes` |
| Kirim berulang tidak menduplikasi | `test_submit_idempotent_and_database_constraint`, `test_simultaneous_registration_submits`, `test_bot_duplicate_update_no_side_effect_and_callback_size` |
| Balasan registrasi persis | `test_registration_resume_edit_mask_and_exact_success` |
| Prasyarat Skrining dan versi riwayat | `test_screening_prerequisite_and_version_history`, `test_bot_screening_review_and_repeat_submission` |
| Pesan tujuh direktori kosong; hanya aktif ditampilkan | `test_empty_directory_seven_categories_only_active` |
| Self asesmen belum aktif tanpa skor | `test_self_assessment_inactive` |
| Kode salah/kedaluwarsa dibatasi | `test_invalid_expired_and_rate_limited_activation` |
| Undangan sekali pakai, termasuk perlombaan transaksi | `test_activation_single_use_hash_and_revoke`, `test_simultaneous_activation_single_winner` |
| Batas lokasi A/B | `test_location_scope_and_ownership`, `test_direct_filters_do_not_expand_location_scope` |
| Pemohon tidak dapat melihat kasus orang lain | `test_location_scope_and_ownership`, `test_forged_bot_update_cannot_switch_case_scope` |
| Progres dan audit sesuai hak akses | `test_progress_audit_and_internal_hidden`, `test_dashboard_assignment_and_progress_post` |
| Catatan internal tidak tampil publik | `test_progress_audit_and_internal_hidden` |
| Kegagalan notifikasi tidak menghapus permohonan | `test_notification_failure_does_not_remove_application` |
| Transisi tidak sah ditolak; buka kembali dibatasi | `test_illegal_transition_and_reopen_rules`, `test_stale_update_rejected` |
| Waktu aware/UTC dan tampilan Asia/Jakarta | `test_web_login_scope_csrf_and_timezone`, `test_public_timestamp_converts_utc_to_jakarta` |

Tes tambahan mencakup duplikasi NIK tanpa pemaparan data orang lain, pembatalan draft tanpa menghapus registrasi resmi, aturan wilayah, penanggung jawab yang tidak sesuai lokasi, draft Skrining yang bertahan saat berpindah menu, rate limit login, CSRF, ketentuan yang tidak bisa diubah diam-diam, persetujuan notifikasi, pencabutan akses saat pengiriman, pengaitan akun institusi berdasarkan pengirim aktual, kedaluwarsa pengaitan, retry mengikuti waktu tunggu Telegram, pengingat idempoten, serta adapter MTProto dengan transport tiruan.

## Screenshot

- [Desktop](dashboard-desktop.png)
- [Ponsel](dashboard-mobile.png)

Screenshot berasal dari database browser sementara, terpisah dari database pengembangan, dan hanya berisi data sintetis. Database pengembangan tidak diisi akun/lokasi/pemohon contoh.

## Hal yang belum dibuktikan

- Koneksi Bot API dan pengiriman Telegram nyata: token belum tersedia; semua pengujian transport menggunakan tiruan.
- Login sesi institusi/MTProto, pembatasan akun nyata, dan jaringan Telegram: API ID/hash/sesi belum tersedia. Akses TCP MTProto tidak dibuktikan oleh akses HTTPS Bot API.
- PostgreSQL produksi, sertifikat/CA database produksi, reverse proxy HTTPS, serta deployment Gunicorn terkelola: belum tersedia. PostgreSQL teruji adalah server lokal sementara melalui Unix socket.
- Direktori/fasilitas, kontak, referensi wilayah resmi, dan instrumen self asesmen: membutuhkan data/penetapan pengelola; tidak direka atau diaktifkan.
- Pemulihan dalam tugas cloud baru dan publikasi environment: tidak diklaim telah diuji.

Koreksi selama validasi: parser koneksi PostgreSQL diperluas untuk URI Unix socket; koneksi thread tes ditutup eksplisit agar teardown database selesai; form penugasan diberi prefix agar ID input unik. Setelah koreksi, suite akhir dan browser berjalan dengan exit 0.
