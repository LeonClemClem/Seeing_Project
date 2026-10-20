# Numerise le graphique "SBIG Seeing Monitor" de ROSA (image RRDtool, fenetre glissante 24 h)
# et ajoute les nouveaux points a un CSV cumulatif.
# Source : https://rosa-remote.com/rosa-live/images/sm.png
#
# Calibration lue dans l'image a chaque execution :
#  - Y : ligne d'axe (valeur 0) + ligne verte horizontale (seuil 2.5 arcsec)
#  - X : lignes verticales horaires (rouge pale) ; l'heure de reference vient de Last-Modified
# Couleurs : rouge = moyenne, bleu = mesure brute (masquee sous le rouge quand les deux coincident).

param(
    [string]$ImagePath,     # optionnel : analyser un PNG local (tests)
    [string]$ExportUtc      # optionnel : CSV en TU de tous les points de l'image (24 h)
)

Add-Type -AssemblyName System.Drawing

$Url       = "https://rosa-remote.com/rosa-live/images/sm.png"
$Dir       = Split-Path -Parent $MyInvocation.MyCommand.Path
$Csv       = Join-Path $Dir "seeing_rosa.csv"
$Log       = Join-Path $Dir "collect-rosa.log"
$Png       = Join-Path $Dir "last_sm.png"
$Header    = "datetime,seeing_moyen_arcsec,seeing_brut_arcsec"
$GreenRef  = 2.5      # valeur du seuil vert (arcsec)

function Write-Log($msg) {
    Add-Content -Path $Log -Value ("{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $msg) -Encoding UTF8
}

# --- Telechargement -----------------------------------------------------------
if ($ImagePath) {
    $Png = $ImagePath
    $refTime = (Get-Item $ImagePath).LastWriteTime
} else {
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $r = Invoke-WebRequest -Uri ("{0}?a={1}" -f $Url, (Get-Random)) -UseBasicParsing -TimeoutSec 60 -OutFile $Png -PassThru
        $refTime = [datetime]::Parse($r.Headers['Last-Modified']).ToLocalTime()
    } catch {
        Write-Log "ERREUR telechargement : $($_.Exception.Message)"
        exit 1
    }
}

$bmp = New-Object System.Drawing.Bitmap $Png
try {
    $W = $bmp.Width; $H = $bmp.Height
    function Px($x, $y) { $bmp.GetPixel($x, $y) }
    function IsGray128($c) { $c.R -eq 128 -and $c.G -eq 128 -and $c.B -eq 128 }
    function IsHourLine($c) { $c.R -eq 162 -and $c.G -eq 110 -and $c.B -eq 110 }
    function IsGreen($c) { $c.G -ge 240 -and $c.R -le 20 -and $c.B -le 20 }
    function IsRed($c) { $c.R -ge 170 -and $c.G -le 110 -and $c.B -le 110 -and ($c.R - $c.G) -ge 90 }
    function IsBlue($c) { $c.B -ge 170 -and $c.R -le 140 -and ($c.B - $c.R) -ge 60 }

    # --- Zone de trace : fond gris 128 --------------------------------------
    $midY = [int]($H / 3)
    $x0 = -1; $x1 = -1
    for ($x = 0; $x -lt $W; $x++) { if (IsGray128 (Px $x $midY)) { if ($x0 -lt 0) { $x0 = $x }; $x1 = $x } }
    # colonne de sonde : celle qui a le plus de fond gris (hors lignes de grille verticales)
    $probeX = $x0 + 1; $bestN = -1; $bestSans = -1; $probeSans = -1
    # 11/10 : la ligne verte ne commence qu'a ~5 px du bord gauche -> la colonne de sonde doit la contenir,
    # et on cherche plus loin si les 30 premieres colonnes n'en ont pas (courbe collee au bord gauche)
    foreach ($lim in @(($x0 + 30), ($x1 - 1))) {
        for ($x = $x0 + 1; $x -le $lim; $x++) {
            $n = 0; $vert = $false; $courbe = $false
            for ($y = 0; $y -lt $H; $y++) {
                $c = Px $x $y
                if (IsGray128 $c) { $n++ } elseif (IsGreen $c) { $vert = $true } elseif ((IsRed $c) -or (IsBlue $c)) { $courbe = $true }
            }
            # colonne sans courbe de mesure (sinon le balayage vertical s'arrete sur la courbe)
            if ($vert -and -not $courbe -and $n -gt $bestN) { $bestN = $n; $probeX = $x }
            if (-not $courbe -and $n -gt $bestSans) { $bestSans = $n; $probeSans = $x }
        }
        if ($bestN -ge 0) { break }
    }
    if ($bestN -lt 0 -and $bestSans -ge 0) { $probeX = $probeSans; $bestN = $bestSans }   # pas de ligne verte
    # haut = premier gris ; axe = rangee juste apres le dernier pixel de fond/grille
    $yTop = -1; $yLastBg = -1
    for ($y = 0; $y -lt $H; $y++) {
        $c = Px $probeX $y
        $bg = (IsGray128 $c) -or ($c.R -eq 133 -and $c.G -eq 133) -or (IsHourLine $c) -or (IsGreen $c)
        if ($bg) { if ($yTop -lt 0) { $yTop = $y }; $yLastBg = $y }
        elseif ($yTop -ge 0 -and ($yLastBg - $yTop) -lt 10) { $yTop = -1; $yLastBg = -1 }   # 11/10 : gris isole (titre)
        elseif ($yTop -ge 0) { break }
    }
    $yAxis = $yLastBg + 1
    if ($x0 -lt 0 -or $yTop -lt 0 -or $yAxis -le $yTop) { throw "zone de trace introuvable" }

    # --- Calibration Y : ligne verte = $GreenRef, affinee par les graduations principales --
    $yGreen = -1
    for ($y = $yTop; $y -lt $yAxis; $y++) { if (IsGreen (Px $probeX $y)) { $yGreen = $y; break } }
    # 11/10 : la ligne verte n'est plus obligatoire. Elle ne sert qu'a choisir le pas des graduations ;
    # sans elle, pas = 1 arcsec (echelles ROSA observees : 0-4, 0-6, toujours graduees de 1 en 1)
    $pxPerUnit = if ($yGreen -ge 0) { ($yAxis - $yGreen) / $GreenRef } else { -1 }
    # graduations principales : rangees avec beaucoup de pixels "ligne rouge pale"
    $major = @()
    for ($y = $yTop; $y -lt $yAxis; $y++) {
        $n = 0; for ($x = $x0; $x -le $x1; $x++) { if (IsHourLine (Px $x $y)) { $n++ } }
        if ($n -ge 100) { $major += $y }
    }
    if ($major.Count -ge 2) {
        $spacing = (($yAxis - $major[0]) / ($major.Count))   # de l'axe (0) a la graduation la plus haute
        if ($pxPerUnit -gt 0) {
            $approxStep = $spacing / $pxPerUnit
            $step = @(0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10) | Sort-Object { [math]::Abs([math]::Log($_ / $approxStep)) } | Select-Object -First 1
        } else { $step = 1.0 }
        $pxPerUnit = $spacing / $step
    }
    if ($pxPerUnit -le 0) { throw "ni ligne verte ni graduations : echelle Y introuvable" }

    # --- Calibration X : lignes horaires ------------------------------------
    # une ligne horaire traverse toute la hauteur : on compte les pixels "ligne horaire" par colonne
    $hourX = @()
    for ($x = $x0; $x -le $x1; $x++) {
        $n = 0
        for ($y = $yTop; $y -lt $yAxis; $y += 3) { if (IsHourLine (Px $x $y)) { $n++ } }
        if ($n -ge 10) { $hourX += $x }
    }
    if ($hourX.Count -lt 4) { throw "lignes horaires introuvables" }
    # regression lineaire x = a + b*k
    $k = 0..($hourX.Count - 1)
    $mk = ($k | Measure-Object -Average).Average; $mx = ($hourX | Measure-Object -Average).Average
    $num = 0; $den = 0
    for ($i = 0; $i -lt $hourX.Count; $i++) { $num += ($k[$i] - $mk) * ($hourX[$i] - $mx); $den += ($k[$i] - $mk) * ($k[$i] - $mk) }
    $pxPerHour = $num / $den
    $secPerPx = 3600 / $pxPerHour
    $xLast = $hourX[-1]
    # l'heure de la derniere ligne : l'heure pleine dont la position predite (bord droit ~ refTime) est la plus proche
    $hourRef = $refTime.Date.AddHours($refTime.Hour)
    $best = $null; $bestD = 1e9
    foreach ($dh in -3..1) {
        $h = $hourRef.AddHours($dh)
        $pred = $x1 - ($refTime - $h).TotalSeconds / $secPerPx
        $d = [math]::Abs($pred - $xLast)
        if ($d -lt $bestD) { $bestD = $d; $best = $h }
    }
    $hourLast = $best

    # --- Extraction des courbes ---------------------------------------------
    $points = New-Object System.Collections.Generic.List[object]
    for ($x = $x0; $x -le $x1; $x++) {
        $red = @(); $blue = @()
        for ($y = $yTop; $y -lt $yAxis; $y++) {
            $c = Px $x $y
            if (IsRed $c) { $red += $y } elseif (IsBlue $c) { $blue += $y }
        }
        if ($red.Count -eq 0 -and $blue.Count -eq 0) { continue }
        $avg = $null; $raw = $null
        if ($red.Count)  { $avg = ($yAxis - (($red  | Measure-Object -Average).Average)) / $pxPerUnit }
        if ($blue.Count) { $raw = ($yAxis - (($blue | Measure-Object -Average).Average)) / $pxPerUnit }
        elseif ($avg -ne $null) { $raw = $avg }   # brut masque sous la moyenne
        $t = $hourLast.AddSeconds(($x - $xLast) * $secPerPx)
        $points.Add([pscustomobject]@{ T = $t; Avg = $avg; Raw = $raw })
    }
} catch {
    Write-Log "ERREUR analyse : $($_.Exception.Message)"
    exit 1
} finally {
    $bmp.Dispose()
}

# --- Ajout au CSV (uniquement les points plus recents que le dernier enregistre) --
$lastT = [datetime]::MinValue
if (Test-Path $Csv) {
    $lastLine = Get-Content $Csv -Tail 1
    $f = $lastLine -split ','
    if ($f[0] -ne 'datetime') { $lastT = [datetime]::ParseExact($f[0], "yyyy-MM-ddTHH:mm:ss", $null) }
} else {
    Set-Content -Path $Csv -Value $Header -Encoding ASCII
}

$inv = [Globalization.CultureInfo]::InvariantCulture
function Fmt($v) { if ($v -eq $null) { "" } else { ([math]::Round($v, 2)).ToString($inv) } }
$new = @($points | Where-Object { $_.T -gt $lastT.AddSeconds($secPerPx / 2) } |
    ForEach-Object { "{0},{1},{2}" -f $_.T.ToString("yyyy-MM-ddTHH:mm:ss"), (Fmt $_.Avg), (Fmt $_.Raw) })

if ($new.Count -gt 0) { Add-Content -Path $Csv -Value $new -Encoding ASCII }

if ($ExportUtc) {
    $tz = [TimeZoneInfo]::FindSystemTimeZoneById("W. Europe Standard Time")   # axe du graphique en heure locale
    $utc = @($points | ForEach-Object {
        "{0},{1},{2}" -f [TimeZoneInfo]::ConvertTimeToUtc([datetime]::SpecifyKind($_.T, 'Unspecified'), $tz).ToString("yyyy-MM-ddTHH:mm:ssZ"), (Fmt $_.Avg), (Fmt $_.Raw) })
    Set-Content -Path $ExportUtc -Value (@("datetime_utc,seeing_moyen_arcsec,seeing_brut_arcsec") + $utc) -Encoding ASCII
}
Write-Log ("OK : {0} nouveau(x) point(s) ; image du {1:yyyy-MM-dd HH:mm} ; {2:N1} s/px ; {3:N2} px/arcsec" -f $new.Count, $refTime, $secPerPx, $pxPerUnit)
