# Downloads the Protomaps basemap extract for Zagreb into data/basemap/zagreb.pmtiles.
#
# Uses the official go-pmtiles CLI (github.com/protomaps/go-pmtiles) to read only the Zagreb
# bounding box from the newest daily planet build with HTTP range requests (tens of MB, not the
# 130 GB planet). Map data: (c) OpenStreetMap contributors, ODbL. Run from the repository root:
#
#   powershell -ExecutionPolicy Bypass -File scripts\fetch-basemap.ps1
#
# Then restart the web server: docker compose up -d web

$ErrorActionPreference = "Stop"
$PmtilesVersion = "1.31.2"
$Bbox = "15.74,45.60,16.26,45.98"   # City of Zagreb with a small margin
$MaxZoom = 15

$Root = Split-Path -Parent $PSScriptRoot
$Target = Join-Path $Root "data\basemap"
$Tools = Join-Path $Target "tools"
New-Item -ItemType Directory -Force $Tools | Out-Null

$Exe = Join-Path $Tools "pmtiles.exe"
if (-not (Test-Path $Exe)) {
    $Zip = Join-Path $Tools "go-pmtiles.zip"
    $Url = "https://github.com/protomaps/go-pmtiles/releases/download/v$PmtilesVersion/go-pmtiles_${PmtilesVersion}_Windows_x86_64.zip"
    Write-Host "Preuzimam pmtiles $PmtilesVersion ..."
    Invoke-WebRequest -Uri $Url -OutFile $Zip
    Expand-Archive -Path $Zip -DestinationPath $Tools -Force
    Remove-Item $Zip
}

# Newest daily build listed by Protomaps.
$Builds = Invoke-RestMethod -Uri "https://build-metadata.protomaps.dev/builds.json"
$Latest = ($Builds | Sort-Object key | Select-Object -Last 1).key
Write-Host "Izvadak iz builda $Latest (bbox $Bbox, zoom do $MaxZoom) ..."

$Out = Join-Path $Target "zagreb.pmtiles"
& $Exe extract "https://build.protomaps.com/$Latest" $Out "--bbox=$Bbox" "--maxzoom=$MaxZoom"
if ($LASTEXITCODE -ne 0) { throw "pmtiles extract nije uspio ($LASTEXITCODE)." }

& $Exe show $Out | Select-Object -First 12
"Build: $Latest`nBbox: $Bbox`nMaxZoom: $MaxZoom`nPreuzeto: $(Get-Date -Format s)" |
    Out-File -Encoding utf8 (Join-Path $Target "SOURCE.txt")
Write-Host "Gotovo: $Out ($([math]::Round((Get-Item $Out).Length / 1MB, 1)) MB)"
