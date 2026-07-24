param(
    [Parameter(Mandatory = $true)]
    [string]$ApiBaseUrl,

    [Parameter(Mandatory = $true)]
    [string]$PublicBaseUrl,

    [switch]$AlsoUpdateRootFiles
)

$ErrorActionPreference = "Stop"

function Normalize-Url {
    param(
        [string]$Value
    )

    if ($null -eq $Value) {
        return ""
    }

    return $Value.Trim().TrimEnd("/")
}

function Update-MetaContent {
    param(
        [string]$FilePath,
        [string]$MetaName,
        [string]$MetaValue
    )

    if (-not (Test-Path $FilePath)) {
        throw "File tidak ditemukan: $FilePath"
    }

    $content = Get-Content -LiteralPath $FilePath -Raw
    $escapedMetaName = [Regex]::Escape($MetaName)
    $pattern = "<meta\s+name=""$escapedMetaName""\s+content=""[^""]*""\s*/?>"
    $replacement = "<meta name=""$MetaName"" content=""$MetaValue"" />"

    $updated = [Regex]::Replace($content, $pattern, $replacement, 1)
    if ($updated -eq $content) {
        throw "Meta tag '$MetaName' tidak ditemukan di $FilePath"
    }

    Set-Content -LiteralPath $FilePath -Value $updated -Encoding UTF8
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$frontendPublicRoot = Join-Path $root "frontend-public"
$rootIndexPath = Join-Path $root "index.html"
$rootAdminPath = Join-Path $root "admin.html"
$publicIndexPath = Join-Path $frontendPublicRoot "index.html"
$publicAdminPath = Join-Path $frontendPublicRoot "admin.html"

$normalizedApiBaseUrl = Normalize-Url -Value $ApiBaseUrl
$normalizedPublicBaseUrl = Normalize-Url -Value $PublicBaseUrl

if (-not $normalizedApiBaseUrl) {
    throw "ApiBaseUrl wajib diisi."
}

if (-not $normalizedPublicBaseUrl) {
    throw "PublicBaseUrl wajib diisi."
}

Update-MetaContent -FilePath $publicIndexPath -MetaName "hydrogis-api-base-url" -MetaValue $normalizedApiBaseUrl
Update-MetaContent -FilePath $publicAdminPath -MetaName "hydrogis-api-base-url" -MetaValue $normalizedApiBaseUrl
Update-MetaContent -FilePath $publicAdminPath -MetaName "hydrogis-public-base-url" -MetaValue $normalizedPublicBaseUrl

if ($AlsoUpdateRootFiles) {
    Update-MetaContent -FilePath $rootIndexPath -MetaName "hydrogis-api-base-url" -MetaValue $normalizedApiBaseUrl
    Update-MetaContent -FilePath $rootAdminPath -MetaName "hydrogis-api-base-url" -MetaValue $normalizedApiBaseUrl
    Update-MetaContent -FilePath $rootAdminPath -MetaName "hydrogis-public-base-url" -MetaValue $normalizedPublicBaseUrl
}

Write-Output "frontend-public siap deploy."
Write-Output "API Base URL    : $normalizedApiBaseUrl"
Write-Output "Public Base URL : $normalizedPublicBaseUrl"
if ($AlsoUpdateRootFiles) {
    Write-Output "Root index/admin juga ikut diperbarui."
}
