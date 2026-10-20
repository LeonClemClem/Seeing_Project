# Releve ponctuel du seeing sur les 3 sites (a lancer a la demande, pas de tache planifiee).
#  - Copernic 05     : nuit en cours (fichier texte du site)
#  - ROSA (Drome)    : dernieres 24 h (graphique PNG numerise)
#  - Saint-Veran     : derniers 7 jours (API Grafana Miratlas)
# Chaque collecteur complete son CSV cumulatif ; ce script ecrit en plus un export en TU
# par site dans releves\<date_heure>\.

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Out  = Join-Path $Root ("releves\" + (Get-Date).ToString("yyyy-MM-dd_HHmm"))
New-Item -ItemType Directory -Force $Out | Out-Null

$sites = @(
    @{ Nom = "Copernic";    Script = "collect-seeing.ps1";             Log = "collect-copernic.log";    Csv = "copernic_UTC.csv" },
    @{ Nom = "ROSA";        Script = "collect-seeing-rosa.ps1";        Log = "collect-rosa.log";        Csv = "rosa_UTC.csv" },
    @{ Nom = "Saint-Veran"; Script = "collect-seeing-saint-veran.ps1"; Log = "collect-saint-veran.log"; Csv = "saint_veran_UTC.csv" }
)

foreach ($s in $sites) {
    $script = Join-Path $Root $s.Script
    $export = Join-Path $Out $s.Csv
    & powershell -NoProfile -ExecutionPolicy Bypass -File $script -ExportUtc $export
    $log = Get-Content (Join-Path $Root $s.Log) -Tail 1
    $n = if (Test-Path $export) { (Get-Content $export).Count - 1 } else { 0 }
    "{0,-12} {1,5} point(s)   {2}" -f $s.Nom, $n, $log
}

Copy-Item (Join-Path $Root "last_sm.png") (Join-Path $Out "rosa_sm.png") -ErrorAction SilentlyContinue
"Exports : $Out"
