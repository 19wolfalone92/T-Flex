param([string]$WorkDirectory = (Join-Path $env:RUNNER_TEMP 'tflex18-native'))
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$evidence = Join-Path $env:GITHUB_WORKSPACE 'native-tflex-evidence'
New-Item -ItemType Directory -Force $WorkDirectory, $evidence | Out-Null

function Get-VerifiedDownload([string]$Url, [string]$Path, [string]$MD5) {
    & curl.exe --fail --location --retry 3 --connect-timeout 30 --max-time 900 --output $Path $Url
    if ($LASTEXITCODE -ne 0) { throw "Official download failed: $Url" }
    if ((Get-FileHash -Algorithm MD5 $Path).Hash.ToLowerInvariant() -ne $MD5) {
        throw 'Vendor-published checksum mismatch; refusing to run the download.'
    }
}

function Invoke-Installer([string]$Arguments, [int]$TimeoutSeconds = 480) {
    $process = Start-Process "$env:WINDIR\System32\msiexec.exe" -ArgumentList $Arguments -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        & taskkill.exe /PID $process.Id /T /F | Out-Null
        throw 'The official Windows installer did not complete.'
    }
    return $process.ExitCode
}

$archive = Join-Path $WorkDirectory 'T-FLEX-CAD-18.zip'
Get-VerifiedDownload 'https://tflex.ru/downloads/V18/T-FLEX%20CAD%2018.zip' $archive 'ac5bc7ed9ef178538554dd1ec7d88691'
$distribution = Join-Path $WorkDirectory 'distribution'
Expand-Archive -LiteralPath $archive -DestinationPath $distribution -Force
$msi = Get-ChildItem -LiteralPath $distribution -Filter '*.msi' -Recurse | Select-Object -First 1
if (-not $msi) { throw 'The official CAD MSI is missing.' }
Remove-Item -LiteralPath $archive

$installedDirectory = Join-Path $WorkDirectory 'installed'
$installLog = Join-Path $evidence 'windows-install.log'
$installCode = Invoke-Installer "/i `"$($msi.FullName)`" /qn /norestart REBOOT=ReallySuppress INSTALLDIR=`"$installedDirectory`" /L*v `"$installLog`""
Write-Host "Official installer exit code: $installCode"

$program = Get-ChildItem -LiteralPath $installedDirectory -Filter 'TFlexAPI.dll' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $program) {
    # Administrative extraction supplies the unmodified vendor runtime and SDK.
    # It creates no trial key or licence metadata and is not reported as an install.
    $extracted = Join-Path $WorkDirectory 'administrative-image'
    $extractLog = Join-Path $evidence 'windows-extract.log'
    $extractCode = Invoke-Installer "/a `"$($msi.FullName)`" /qn TARGETDIR=`"$extracted`" /L*v `"$extractLog`""
    if ($extractCode -ne 0) { throw "Official administrative extraction failed: $extractCode" }
    $program = Get-ChildItem -LiteralPath $extracted -Filter 'TFlexAPI.dll' -Recurse | Select-Object -First 1
}
if (-not $program) { throw 'No official T-FLEX API assembly was found.' }
$programDirectory = $program.Directory.FullName
Write-Host "Vendor API directory: $programDirectory"

$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$executable = Join-Path $evidence 'ProbeTflexSession.exe'
$source = Join-Path $PSScriptRoot 'ProbeTflexSession.cs'
& $compiler /nologo /target:exe /platform:x64 /reference:System.Xml.dll "/out:$executable" $source
if ($LASTEXITCODE -ne 0) { throw 'Native .NET probe compilation failed.' }
Copy-Item -LiteralPath $source -Destination $evidence

$stdout = Join-Path $evidence 'api-probe.stdout.txt'
$stderr = Join-Path $evidence 'api-probe.stderr.txt'
$probe = Start-Process $executable -ArgumentList "`"$programDirectory`" `"$evidence`"" -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$completed = $probe.WaitForExit(180000)
if (-not $completed) { & taskkill.exe /PID $probe.Id /T /F | Out-Null }
$result = [ordered]@{
    official_installer_exit_code = $installCode
    probe_completed = $completed
    probe_exit_code = $(if ($completed) { $probe.ExitCode } else { $null })
    writable_session_available = ($completed -and $probe.ExitCode -eq 0)
    native_figurine_grb_created = $false
    licence_data_modified_by_probe = $false
    trial_activated_by_probe = $false
}
$result | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $evidence 'probe-result.json')
Get-Content -LiteralPath $stdout
Get-Content -LiteralPath $stderr
if (-not $result.writable_session_available) { throw 'A normal writable T-FLEX session could not be established. No .grb is claimed.' }
