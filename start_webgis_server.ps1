param(
  [int]$Port = 8000,
  [ValidateSet("local", "staging", "production")]
  [string]$AppEnvironment = "local",
  [string]$AppEnvironmentLabel = "",
  [string]$AppName = "FloodGIS Jakarta Timur"
)

$python = "C:\Users\Vino\anaconda3\envs\tf_env\python.exe"
$script = Join-Path $PSScriptRoot "backend_fastapi\run.py"

if ([string]::IsNullOrWhiteSpace($AppEnvironmentLabel)) {
  $AppEnvironmentLabel = $AppEnvironment.ToUpperInvariant()
}

if (-not (Test-Path -LiteralPath $python)) {
  Write-Error "Python tf_env tidak ditemukan di $python"
  exit 1
}

if (-not (Test-Path -LiteralPath $script)) {
  Write-Error "File backend tidak ditemukan di $script"
  exit 1
}

Write-Host "Menjalankan $AppName [$AppEnvironmentLabel] di http://localhost:$Port/"
Write-Host "Halaman peta: http://localhost:$Port/"
Write-Host "Halaman admin: http://localhost:$Port/admin.html"
Write-Host "Endpoint API prediksi: http://localhost:$Port/api/predictions"
Write-Host "Tekan Ctrl+C di terminal ini kalau sudah selesai."

$env:APP_ENV = $AppEnvironment
$env:APP_ENV_LABEL = $AppEnvironmentLabel
$env:APP_NAME = $AppName

& $python $script --port $Port --host 127.0.0.1
