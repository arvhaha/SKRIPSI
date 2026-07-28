$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$reactRoot = Join-Path $root "frontend-react"
$distRoot = Join-Path $reactRoot "dist"
$frontendPublicRoot = Join-Path $root "frontend-public"
$dataRoot = Join-Path $root "data"
$skipBuild = $args -contains "--skip-build"

if (-not (Test-Path $reactRoot)) {
    throw "Folder frontend-react tidak ditemukan."
}

if (-not $skipBuild) {
    Push-Location $reactRoot
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) {
            throw "Build React gagal."
        }
    }
    finally {
        Pop-Location
    }
}

if (-not (Test-Path $distRoot)) {
    throw "Folder dist React belum tersedia. Jalankan build terlebih dahulu."
}

New-Item -ItemType Directory -Force -Path $frontendPublicRoot | Out-Null
$rootReactAssets = Join-Path $root "react-assets"
$publicReactAssets = Join-Path $frontendPublicRoot "react-assets"
$distDataRoot = Join-Path $distRoot "data"
$publicDataRoot = Join-Path $frontendPublicRoot "data"

if (Test-Path $rootReactAssets) {
    Remove-Item -LiteralPath $rootReactAssets -Recurse -Force
}

if (Test-Path $publicReactAssets) {
    Remove-Item -LiteralPath $publicReactAssets -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $rootReactAssets | Out-Null
New-Item -ItemType Directory -Force -Path $publicReactAssets | Out-Null
New-Item -ItemType Directory -Force -Path $distDataRoot | Out-Null
New-Item -ItemType Directory -Force -Path $publicDataRoot | Out-Null

Copy-Item -LiteralPath (Join-Path $distRoot "index.html") -Destination (Join-Path $root "index.html") -Force
Copy-Item -LiteralPath (Join-Path $distRoot "admin.html") -Destination (Join-Path $root "admin.html") -Force
Copy-Item -LiteralPath (Join-Path $distRoot "index.html") -Destination (Join-Path $frontendPublicRoot "index.html") -Force
Copy-Item -LiteralPath (Join-Path $distRoot "admin.html") -Destination (Join-Path $frontendPublicRoot "admin.html") -Force

Copy-Item -Path (Join-Path $distRoot "react-assets\*") -Destination $rootReactAssets -Recurse -Force
Copy-Item -Path (Join-Path $distRoot "react-assets\*") -Destination $publicReactAssets -Recurse -Force

$dataFiles = @(
    "east-jakarta-predictions.json",
    "jkt.geojson"
)

foreach ($fileName in $dataFiles) {
    $sourcePath = Join-Path $dataRoot $fileName
    if (Test-Path $sourcePath) {
        Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $distDataRoot $fileName) -Force
        Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $publicDataRoot $fileName) -Force
    }
}

Write-Output "React frontend utama berhasil disinkronkan ke root project, frontend-public, dan snapshot data statis terbaru."
