# T-FLEX CAD 18 external-user-command bridge. Requires Python package + Blender 4.x.
# Does NOT pretend to use the unavailable native T-FLEX Open API or convert STL to NURBS.
param(
    [string] $InputModel,
    [double] $HeightMM = 120,
    [double] $CutRatio = 0.50,
    [double] $PinMM = 3.0,
    [double] $ClearanceMM = 0.20,
    [string] $UpAxis = "",
    [switch] $SemanticParts
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
if ([string]::IsNullOrWhiteSpace($InputModel)) {
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Filter = '3D models (*.glb;*.obj;*.stl)|*.glb;*.obj;*.stl'
    $dlg.Title = 'T-FLEX Studio - выбрать модель фигурки'
    if ($dlg.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit 0 }
    $InputModel = $dlg.FileName
}
if (-not (Test-Path -LiteralPath $InputModel -PathType Leaf)) {
    throw "3D model was not found: $InputModel"
}
$py = Get-Command 'py.exe' -ErrorAction SilentlyContinue
if ($null -eq $py) { throw 'Install Python 3.11 and run: py -3 -m pip install -e .[dev] in repository' }
$blender = Get-Command 'blender.exe' -ErrorAction SilentlyContinue
if ($null -ne $blender) { $blenderPath = $blender.Source }
else {
    $candidates = Get-ChildItem -Path (Join-Path $env:ProgramFiles 'Blender Foundation') -Directory -ErrorAction SilentlyContinue |
        Sort-Object -Property Name -Descending
    $blenderPath = $null
    foreach ($dir in $candidates) {
        $candidate = Join-Path $dir.FullName 'blender.exe'
        if (Test-Path -LiteralPath $candidate) { $blenderPath = $candidate; break }
    }
}
if ([string]::IsNullOrWhiteSpace($blenderPath)) {
    throw 'Install Blender 4.x and put blender.exe on PATH, or in Program Files/Blender Foundation.'
}
if ($HeightMM -le 20 -or $HeightMM -ge 1000) { throw 'HeightMM must be 20..1000 mm' }
$base = [System.IO.Path]::GetFileNameWithoutExtension($InputModel)
$safeBase = $base -replace '[^a-zA-Z0-9_\-]', '_'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$target = Join-Path ([Environment]::GetFolderPath('MyDocuments')) "T-FLEX-Figurines\$safeBase-$stamp-$(Get-Random -Maximum 100000)"
$ready = Join-Path $target 'prepared'
$parts = Join-Path $target 'assembly-pieces'
New-Item -ItemType Directory -Path $target -Force | Out-Null
$height = $HeightMM.ToString([System.Globalization.CultureInfo]::InvariantCulture)
$ratio = $CutRatio.ToString([System.Globalization.CultureInfo]::InvariantCulture)
$pin = $PinMM.ToString([System.Globalization.CultureInfo]::InvariantCulture)
$clearance = $ClearanceMM.ToString([System.Globalization.CultureInfo]::InvariantCulture)
if ([string]::IsNullOrWhiteSpace($UpAxis)) {
    $ext = [System.IO.Path]::GetExtension($InputModel).ToLowerInvariant()
    $UpAxis = if ($ext -in @(".glb", ".gltf")) { "y" } else { "z" }
}
if ($UpAxis -notin @("x", "y", "z")) { throw "UpAxis must be x/y/z" }
if ($SemanticParts) {
    Write-Host 'Hi3D semantic multi-part GLB: extracting *existing* separate pieces...'
    & $py.Source -3 -m tflex_figurines.parts "$InputModel" --height-mm "$height" --output-dir "$parts"
    if ($LASTEXITCODE -ne 0) { throw "Semantic extraction blocked; original model needs manual repair" }
    Write-Host "Independent print STLs, CAD-aligned STLs and BOM are in $parts"
    Write-Host 'Verify each pin/ball/dovetail joint with a test print and physical fit.'
    Start-Process explorer.exe -ArgumentList ('"' + $parts + '"')
    exit 0
}
Write-Host "Preflight source geometry and orient it (height $height mm, axis $UpAxis)..."
& $py.Source -3 -m tflex_figurines.pipeline "$InputModel" --height-mm "$height" --up-axis "$UpAxis" --output-dir "$ready"
if ($LASTEXITCODE -ne 0) { throw "Geometry preflight failed; inspect $ready before print splitting" }
$prepared = Join-Path (Join-Path $ready 'exports') "$base.stl"
if (-not (Test-Path -LiteralPath $prepared)) { throw 'Prepared STL not produced' }
Write-Host "Splitting the valid STL with real Blender (FDM)..."
& $py.Source -3 -m tflex_figurines.splitter "$prepared" --output-dir "$parts" --blender "$blenderPath" --cut-ratio "$ratio" --pin-diameter-mm "$pin" --clearance-mm "$clearance"
if ($LASTEXITCODE -ne 0) { throw "Blender split failed; $parts is NOT print-ready" }
Write-Host "STL print parts are in $parts\print; assembly-aligned mesh parts in $parts\assembly"
Write-Host 'Print a fit-test socket first. Review orientation, wall thickness and supports in slicer.'
Start-Process explorer.exe -ArgumentList ('"' + $parts + '"')
