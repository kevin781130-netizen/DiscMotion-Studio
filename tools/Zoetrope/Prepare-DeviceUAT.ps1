# Windows 11: generate a real-CD-R test image; never burns a disc.
# .NET 10 SDK required; no Docker/Python/GitHub Actions.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Frames,
      [Parameter(Mandatory=$true)][string]$OutDir)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
function Check-Exit([string]$step) { if ($LASTEXITCODE -ne 0) { throw "$step failed: $LASTEXITCODE" } }
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$framesDir=(Resolve-Path -LiteralPath $Frames -ErrorAction Stop).Path
if (-not (Test-Path -LiteralPath $framesDir -PathType Container)) { throw "Frames must be a directory" }
$dest=[IO.Path]::GetFullPath($OutDir)
if ((Test-Path -LiteralPath $dest) -and @(Get-ChildItem -LiteralPath $dest -Force).Count -gt 0) {
    throw "OutDir must be new or empty (never overwrite outputs)"
}
$files=@(Get-ChildItem -LiteralPath $framesDir -File | Where-Object {
    @('.png','.jpg','.jpeg','.bmp','.gif') -contains $_.Extension.ToLowerInvariant()
})
if ($files.Count -ne 12) { throw "Expected 12 image frames, found $($files.Count)" }
for ($i=0;$i -lt 12;$i++) {
    $stem='{0:D2}' -f $i
    if (@($files | Where-Object { $_.BaseName -ceq $stem }).Count -ne 1) {
        throw "Frame index missing or duplicated: $stem (use 00 to 11)"
    }
}
if ($null -eq (Get-Command dotnet -ErrorAction SilentlyContinue)) { throw ".NET 10 SDK not installed" }
$sdk=(& dotnet --version).Trim()
Check-Exit 'SDK check'
if ($sdk -notmatch '^10\.') { throw "Expected .NET 10 SDK, found $sdk" }
$zoetrope=Join-Path $root 'tools\Zoetrope\Zoetrope.csproj'
$cli=Join-Path $root 'src\DiscImageStudio.Cli\DiscImageStudio.Cli.csproj'
$render=Join-Path $dest 'render'
$burnDir=Join-Path $dest 'burn'
$wave=Join-Path $burnDir 'disc-zoetrope.wav'
$cue=Join-Path $burnDir 'disc-zoetrope.cue'
$sectors=359849
$payload=[int64]$sectors*2352L
if (-not (Test-Path -LiteralPath $zoetrope) -or -not (Test-Path -LiteralPath $cli)) {
    throw 'Missing project sources'
}
New-Item -ItemType Directory -Path $burnDir -Force | Out-Null
Push-Location $root
try {
    & dotnet run --project $zoetrope -c Release -- render --frames $framesDir --out $render
    Check-Exit '12-frame render'
    & dotnet run --project $cli -c Release -- cd-generate --input (Join-Path $render 'disc.png') --output $wave --sectors $sectors --r0 24.5 --r1 56.8 --outer 57.5 --tone-dither 1 --tone-levels 2 --interleave true --cue true
    Check-Exit 'CD-DA WAV/CUE generation'
} finally { Pop-Location }
if (-not (Test-Path -LiteralPath $wave) -or -not (Test-Path -LiteralPath $cue) -or -not (Test-Path -LiteralPath ($wave+'.json'))) {
    throw 'Missing WAV, CUE, or metadata'
}
if ((Get-Item -LiteralPath $wave).Length -ne ($payload+44L)) { throw 'Full CD size mismatch' }
$stream=[IO.File]::OpenRead($wave)
try {
    $h=New-Object byte[] 44
    if ($stream.Read($h,0,44) -ne 44) { throw 'WAV truncated' }
    if ([Text.Encoding]::ASCII.GetString($h,0,4) -ne 'RIFF' -or
        [Text.Encoding]::ASCII.GetString($h,8,4) -ne 'WAVE' -or
        [Text.Encoding]::ASCII.GetString($h,36,4) -ne 'data') { throw 'WAV header invalid' }
    if ([BitConverter]::ToUInt32($h,40) -ne $payload -or
        [BitConverter]::ToUInt32($h,24) -ne 44100 -or
        [BitConverter]::ToUInt16($h,22) -ne 2 -or
        [BitConverter]::ToUInt16($h,34) -ne 16) { throw 'CD-DA PCM metadata invalid' }
    $stream.Seek(-2352,[IO.SeekOrigin]::End) | Out-Null
    $tail=New-Object byte[] 2352
    if ($stream.Read($tail,0,2352) -ne 2352) { throw 'Last sector missing' }
} finally { $stream.Dispose() }
$c=Get-Content -LiteralPath $cue -Raw
if (-not $c.Contains('FILE "disc-zoetrope.wav" WAVE') -or
    -not $c.Contains('TRACK 01 AUDIO')) { throw 'CUE mismatch' }
$m=Get-Content -LiteralPath ($wave+'.json') -Raw | ConvertFrom-Json
if ($m.format -ne 'cd-da-track-v1' -or [int64]$m.sectors -ne $sectors -or
    $m.interleaved -ne $true -or $m.toneLevels -ne 2) { throw 'Track sidecar mismatch' }
$rev='UNKNOWN'
if ((Test-Path -LiteralPath (Join-Path $root '.git')) -and
    $null -ne (Get-Command git -ErrorAction SilentlyContinue)) {
    $rev=(( & git -C $root rev-parse HEAD ) | Select-Object -First 1).Trim()
}
$report=[ordered]@{
    gate='WINDOWS_ARTIFACT_PREP_PASS'
    source_commit=$rev
    dotnet_sdk=$sdk
    sectors=$sectors
    wave_bytes=($payload+44L)
    wave_sha256=(Get-FileHash -LiteralPath $wave -Algorithm SHA256).Hash.ToLowerInvariant()
    png_sha256=(Get-FileHash -LiteralPath (Join-Path $render 'disc.png') -Algorithm SHA256).Hash.ToLowerInvariant()
    wav_path=$wave
    cue_path=$cue
    preview_path=(Join-Path $render 'preview.html')
    physical_burn='NOT_RUN'
    physical_optics='NOT_RUN'
    contains_listenable_music=$false
}
$reportPath=Join-Path $dest 'PRE_DEVICE_REPORT.json'
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $reportPath -Encoding UTF8
Write-Host "WINDOWS_ARTIFACT_PREP_PASS: $reportPath"
Write-Host 'Physical CD-R / optics: NOT_RUN'
