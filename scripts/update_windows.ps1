$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) {
    throw 'Folder .venv belum ada. Jalankan py -m venv .venv terlebih dahulu.'
}
Write-Host 'Pastikan server dashboard, bot, dan worker lama sudah dihentikan dengan Ctrl+C.'
& $python scripts/backup_local.py
if ($LASTEXITCODE -ne 0) { throw 'Backup belum berhasil. Migrasi tidak dijalankan.' }
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Pemasangan dependensi gagal.' }
& $python manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { throw 'Migrasi gagal. Simpan pesan error tanpa token.' }
& $python manage.py check
if ($LASTEXITCODE -ne 0) { throw 'Pemeriksaan aplikasi gagal.' }
Write-Host 'Pembaruan selesai. Jalankan dashboard dan run_bot di dua terminal terpisah.'
