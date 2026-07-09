param(
  [string]$PythonPath = "C:\Users\Vino\anaconda3\envs\tf_env\python.exe",
  [ValidateSet("local", "staging", "production")]
  [string]$AppEnvironment = "local",
  [string]$AppEnvironmentLabel = "",
  [string]$AppName = "FloodGIS Jakarta Timur",
  [int]$BackfillDays = 3,
  [string]$EndDate = "",
  [switch]$SkipSourceUpdate
)

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$datasetUpdater = Join-Path $root "update_openmeteo_dataset_jaktim.py"
$backendScript = Join-Path $root "webgis_backend.py"
$logDir = Join-Path $root "artifacts\scheduler_logs"
$runStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logPath = Join-Path $logDir "daily_refresh_$runStamp.log"

New-Item -ItemType Directory -Path $logDir -Force | Out-Null

function Write-Log {
  param([string]$Message)
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Write-Host $line
  Add-Content -LiteralPath $logPath -Value $line
}

function Invoke-And-Log {
  param(
    [string]$FilePath,
    [string[]]$Arguments
  )

  $stdoutPath = Join-Path $logDir ("stdout_" + [guid]::NewGuid().ToString("N") + ".log")
  $stderrPath = Join-Path $logDir ("stderr_" + [guid]::NewGuid().ToString("N") + ".log")

  try {
    $process = Start-Process `
      -FilePath $FilePath `
      -ArgumentList $Arguments `
      -WorkingDirectory $root `
      -WindowStyle Hidden `
      -Wait `
      -PassThru `
      -RedirectStandardOutput $stdoutPath `
      -RedirectStandardError $stderrPath

    foreach ($path in @($stdoutPath, $stderrPath)) {
      if (Test-Path -LiteralPath $path) {
        Get-Content -LiteralPath $path | ForEach-Object {
          Write-Host $_
          Add-Content -LiteralPath $logPath -Value $_
        }
      }
    }

    if ($process.ExitCode -ne 0) {
      throw "Perintah gagal: $FilePath $($Arguments -join ' ')"
    }
  }
  finally {
    Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
  }
}

if (-not (Test-Path -LiteralPath $PythonPath)) {
  throw "Python environment tidak ditemukan di $PythonPath"
}

if (-not (Test-Path -LiteralPath $datasetUpdater)) {
  throw "File updater dataset tidak ditemukan di $datasetUpdater"
}

if (-not (Test-Path -LiteralPath $backendScript)) {
  throw "File backend tidak ditemukan di $backendScript"
}

if ([string]::IsNullOrWhiteSpace($AppEnvironmentLabel)) {
  $AppEnvironmentLabel = $AppEnvironment.ToUpperInvariant()
}

Write-Log "Mulai job scheduler harian HydroGIS."
Write-Log "Log file: $logPath"
Write-Log "Environment: $AppEnvironmentLabel"

if (-not $SkipSourceUpdate) {
  $updateArgs = @(
    $datasetUpdater,
    "--backfill-days",
    $BackfillDays.ToString()
  )

  if (-not [string]::IsNullOrWhiteSpace($EndDate)) {
    $updateArgs += @("--end-date", $EndDate)
  }

  Write-Log "Langkah 1/2: update dataset cuaca incremental."
  Invoke-And-Log -FilePath $PythonPath -Arguments $updateArgs
}
else {
  Write-Log "Langkah 1/2: dilewati. Dataset sumber tidak di-update."
}

$env:APP_ENV = $AppEnvironment
$env:APP_ENV_LABEL = $AppEnvironmentLabel
$env:APP_NAME = $AppName

Write-Log "Langkah 2/2: export prediksi statis ke data/east-jakarta-predictions.json."
Invoke-And-Log -FilePath $PythonPath -Arguments @(
  $backendScript,
  "--export-static-json",
  "--no-serve"
)

Write-Log "Job scheduler harian selesai tanpa error."
