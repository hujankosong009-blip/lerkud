from django.db import migrations
BODY = '''SALAM MANIS (Sadar Lapor Mandiri – Akses Mudah, Aman, Humanis) bertujuan memudahkan masyarakat mengakses wajib lapor dan rehabilitasi narkotika melalui BNN Kota Surabaya dan jejaring layanan.

Data yang dikumpulkan meliputi identitas akun Telegram, NIK, nama, nomor telepon, alamat domisili, uraian permasalahan awal, persetujuan, dan riwayat permohonan.

Data digunakan untuk registrasi serta tindak lanjut layanan dan hanya diakses petugas sesuai kewenangan serta lokasi penugasannya. Pemohon wajib mengisi data dengan benar.

Skrining melalui bot berupa penyampaian permasalahan awal, bukan instrumen klinis tervalidasi dan tidak menghasilkan diagnosis atau keputusan layanan.

Self asesmen tidak menggantikan asesmen oleh petugas. Fitur ini belum aktif sampai instrumen ditetapkan pengelola yang berwenang.

Pengajuan melalui bot tidak berarti layanan telah selesai diproses. Pemohon dapat memantau progres permohonannya. Status Selesai berarti proses permohonan ditutup sesuai catatan petugas; tidak berarti sembuh atau rehabilitasi berhasil.

Alamat diisi manual dan belum terverifikasi. Pemeriksaan format NIK bukan verifikasi Dukcapil. Notifikasi opsional hanya dikirim setelah persetujuan dan mengikuti konfigurasi kanal.'''
def seed(apps,schema_editor):
    Terms=apps.get_model('service','Terms')
    Terms.objects.get_or_create(version='1.0',defaults={'body':BODY,'active':not Terms.objects.filter(active=True).exists()})
class Migration(migrations.Migration):
    dependencies=[('service','0001_initial')]
    operations=[migrations.RunPython(seed,migrations.RunPython.noop)]
