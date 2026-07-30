param(
  [string]$TaskName = "HydroGIS Daily Prediction Refresh",
  [string]$Time = "04:00",
  [string]$PythonPath = "C:\Users\Vino\anaconda3\envs\tf_env\python.exe",
  [ValidateSet("local", "staging", "production")]
  [string]$AppEnvironment = "local",
  [string]$AppEnvironmentLabel = "",
  [string]$AppName = "FloodGIS Jakarta Timur",
  [int]$BackfillDays = 3,
  [int]$SourceLagDays = 1,
  [switch]$SkipSourceUpdate,
  [switch]$PreviewOnly
)

$ErrorActionPreference = "Stop"

if ($Time -notmatch '^\d{2}:\d{2}$') {
  throw "Format -Time harus HH:mm, misalnya 05:30"
}

if (-not (Test-Path -LiteralPath $PythonPath)) {
  throw "Python environment tidak ditemukan di $PythonPath"
}

$refreshScript = Join-Path $PSScriptRoot "refresh_daily_predictions.ps1"
if (-not (Test-Path -LiteralPath $refreshScript)) {
  throw "File refresh harian tidak ditemukan di $refreshScript"
}

if ([string]::IsNullOrWhiteSpace($AppEnvironmentLabel)) {
  $AppEnvironmentLabel = $AppEnvironment.ToUpperInvariant()
}

$argumentParts = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", "`"$refreshScript`"",
  "-PythonPath", "`"$PythonPath`"",
  "-AppEnvironment", $AppEnvironment,
  "-AppEnvironmentLabel", "`"$AppEnvironmentLabel`"",
  "-AppName", "`"$AppName`"",
  "-BackfillDays", $BackfillDays.ToString(),
  "-SourceLagDays", $SourceLagDays.ToString()
)

if ($SkipSourceUpdate) {
  $argumentParts += "-SkipSourceUpdate"
}

$actionArguments = $argumentParts -join " "
$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$startAt = [datetime]::ParseExact($Time, "HH:mm", $null)

Write-Host "Task Name : $TaskName"
Write-Host "User      : $currentUser"
Write-Host "Time      : $Time"
Write-Host "Action    : powershell.exe $actionArguments"

if ($PreviewOnly) {
  Write-Host "PreviewOnly aktif. Task belum didaftarkan."
  return
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArguments
$trigger = New-ScheduledTaskTrigger -Daily -At $startAt
$principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Principal $principal `
  -Settings $settings `
  -Description "Refresh dataset Open-Meteo dan ekspor prediksi harian HydroGIS." `
  -Force | Out-Null

Write-Host "Task scheduler harian berhasil didaftarkan."
Write-Host "Cek log nanti di artifacts\\scheduler_logs"
