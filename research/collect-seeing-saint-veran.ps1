# Collecte le seeing de Saint-Veran depuis le tableau de bord Grafana de Miratlas
# (panneau "Seeing scaled to zenith at 550nm") et l'ajoute a un CSV cumulatif en TU.
# Source : https://dashboard.miratlas.net/d/cdzuviwylbfggb/fr-saint-veran-7-days?orgId=29
# Mesures brutes (sans moyenne glissante), memes filtres que le tableau de bord (0 < seeing <= 10).
# Horodatages en TU (InfluxDB).

param(
    [int]$Days = 7,            # profondeur recuperee (le tableau de bord montre 7 jours)
    [string]$ExportUtc         # optionnel : CSV des donnees de la fenetre recuperee
)

$Api    = "https://dashboard.miratlas.net/api/ds/query?orgId=29"
$DsUid  = "ddzuval7sgglcb"
$Dir    = Split-Path -Parent $MyInvocation.MyCommand.Path
$Csv    = Join-Path $Dir "seeing_saint_veran.csv"
$Log    = Join-Path $Dir "collect-saint-veran.log"
# colonne CSV -> (measurement, field)
$Series = [ordered]@{
    day_ssm_arcsec        = @("ism_stations", "day_see")
    day_ssm_stddev_arcsec = @("ism_stations", "day_see_stddev")
    night_cdimm_arcsec    = @("ism_stations", "night_see")
    day_shabar_arcsec     = @("shabar", "seeing")
}
$Cols   = @($Series.Keys)
$Header = "datetime_utc," + ($Cols -join ',')

function Write-Log($msg) {
    Add-Content -Path $Log -Value ("{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $msg) -Encoding UTF8
}

# --- Requete ------------------------------------------------------------------
$start = (Get-Date).ToUniversalTime().AddDays(-$Days).ToString("yyyy-MM-ddTHH:mm:ssZ")
$queries = @()
foreach ($col in $Cols) {
    $m, $f = $Series[$col]
    $flux = "from(bucket: `"miratlas`")`n  |> range(start: $start, stop: v.timeRangeStop)`n" +
            "  |> filter(fn: (r) => r._measurement == `"$m`" and r._field == `"$f`")`n" +
            "  |> filter(fn: (r) => r._value > 0 and r._value <= 10)`n" +
            "  |> group(columns: [`"_field`"])"
    $queries += @{ refId = $col; datasource = @{ type = "influxdb"; uid = $DsUid }; query = $flux; maxDataPoints = 100000 }
}
$body = @{ queries = $queries; from = "now-$($Days)d"; to = "now" } | ConvertTo-Json -Depth 6

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $res = Invoke-RestMethod -Method Post -Uri $Api -ContentType "application/json" -Body $body -TimeoutSec 120
} catch {
    Write-Log "ERREUR requete : $($_.Exception.Message)"
    exit 1
}

# --- Mise en table large : une ligne par horodatage ----------------------------
$inv = [Globalization.CultureInfo]::InvariantCulture
$table = @{}
foreach ($col in $Cols) {
    $r = $res.results.$col
    if ($r.error) { Write-Log "ERREUR serie $col : $($r.error)"; exit 1 }
    foreach ($frame in @($r.frames)) {
        if (-not $frame) { continue }
        $t = $frame.data.values[0]; $v = $frame.data.values[1]
        for ($i = 0; $i -lt $t.Count; $i++) {
            $ts = [DateTimeOffset]::FromUnixTimeMilliseconds([long]$t[$i]).UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ssZ")
            if (-not $table.ContainsKey($ts)) { $table[$ts] = @{} }
            $table[$ts][$col] = ([math]::Round([double]$v[$i], 3)).ToString($inv)
        }
    }
}
$rows = foreach ($ts in ($table.Keys | Sort-Object)) {
    $ts + "," + (($Cols | ForEach-Object { $table[$ts][$_] }) -join ',')
}

# --- Ajout au CSV cumulatif (horodatages absents uniquement) ------------------
$known = New-Object 'System.Collections.Generic.HashSet[string]'
if (Test-Path $Csv) {
    Get-Content $Csv | Select-Object -Skip 1 | ForEach-Object { [void]$known.Add(($_ -split ',')[0]) }
} else {
    Set-Content -Path $Csv -Value $Header -Encoding ASCII
}
$new = @($rows | Where-Object { $known.Add(($_ -split ',')[0]) })
if ($new.Count -gt 0) { Add-Content -Path $Csv -Value $new -Encoding ASCII }

if ($ExportUtc) { Set-Content -Path $ExportUtc -Value (@($Header) + @($rows)) -Encoding ASCII }

$counts = ($Cols | ForEach-Object { $c = $_; "$c=" + @($table.Values | Where-Object { $_.ContainsKey($c) }).Count }) -join ' '
Write-Log "OK : $($new.Count) nouvelle(s) ligne(s) ; fenetre $Days j ; $counts"
