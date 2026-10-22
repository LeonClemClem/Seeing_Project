# Collecte le seeing de l'Association Copernic 05 et l'ajoute a un CSV cumulatif.
# Source : https://www.asso-copernic.org/seeing/data.txt (date,heure,scintillation,seeing)
# Le fichier source ne contient que la nuit en cours : on fusionne sans doublons.

param([string]$ExportUtc)   # optionnel : CSV en TU de la nuit en cours (contenu du fichier source)

$Url     = "https://www.asso-copernic.org/seeing/data.txt"
$Here    = Split-Path -Parent $MyInvocation.MyCommand.Path
$CfgFile = Join-Path $Here "chemins_locaux.json"
$Mes     = if ($env:SEEING_MESURES) { $env:SEEING_MESURES } elseif (Test-Path $CfgFile) { (Get-Content $CfgFile -Raw | ConvertFrom-Json).mesures } else { $null }
if (-not $Mes) { $Mes = Join-Path (Split-Path -Parent $Here) "donnees\mesures" }   # voir chemins.py
$Dir     = Join-Path $Mes "seeing-copernic"
New-Item -ItemType Directory -Force $Dir | Out-Null
$Csv     = Join-Path $Dir "seeing_copernic.csv"
$Log     = Join-Path $Dir "collect.log"
$Header  = "datetime,date,heure,scintillation,seeing_arcsec"

function Write-Log($msg) {
    Add-Content -Path $Log -Value ("{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $msg) -Encoding UTF8
}

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $content = (Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 60).Content
} catch {
    Write-Log "ERREUR telechargement : $($_.Exception.Message)"
    exit 1
}

# Cles deja presentes (colonne datetime)
$known = New-Object 'System.Collections.Generic.HashSet[string]'
if (Test-Path $Csv) {
    Get-Content $Csv | Select-Object -Skip 1 | ForEach-Object { [void]$known.Add(($_ -split ',')[0]) }
} else {
    Set-Content -Path $Csv -Value $Header -Encoding ASCII
}

$new = New-Object System.Collections.Generic.List[string]
$utc = New-Object System.Collections.Generic.List[string]
$tz  = [TimeZoneInfo]::FindSystemTimeZoneById("W. Europe Standard Time")   # source en heure locale (TU+1/TU+2)
foreach ($line in ($content -split "`r?`n")) {
    $f = $line.Trim() -split ','
    if ($f.Count -lt 4) { continue }
    try {
        $dt = [datetime]::ParseExact("$($f[0]) $($f[1])", "dd/MM/yyyy HH:mm:ss", $null)
    } catch { continue }
    $iso = $dt.ToString("yyyy-MM-ddTHH:mm:ss")
    if ($known.Add($iso)) {
        $new.Add("$iso,$($f[0]),$($f[1]),$($f[2]),$($f[3])")
    }
    $utc.Add(("{0},{1},{2}" -f [TimeZoneInfo]::ConvertTimeToUtc($dt, $tz).ToString("yyyy-MM-ddTHH:mm:ssZ"), $f[2], $f[3]))
}

if ($new.Count -gt 0) { Add-Content -Path $Csv -Value $new -Encoding ASCII }
if ($ExportUtc) { Set-Content -Path $ExportUtc -Value (@("datetime_utc,scintillation,seeing_arcsec") + @($utc)) -Encoding ASCII }
Write-Log "OK : $($new.Count) nouvelle(s) ligne(s)"
