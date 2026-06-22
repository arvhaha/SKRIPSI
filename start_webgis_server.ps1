$port = 8000
$python = "C:\Users\Vino\anaconda3\envs\tf_env\python.exe"
$script = Join-Path $PSScriptRoot "webgis_backend.py"

if (-not (Test-Path -LiteralPath $python)) {
  Write-Error "Python tf_env tidak ditemukan di $python"
  exit 1
}

if (-not (Test-Path -LiteralPath $script)) {
  Write-Error "File backend tidak ditemukan di $script"
  exit 1
}

Write-Host "Menjalankan FloodGIS + backend model di http://localhost:$port/"
Write-Host "Endpoint API prediksi: http://localhost:$port/api/predictions"
Write-Host "Tekan Ctrl+C di terminal ini kalau sudah selesai."

& $python $script --port $port
