# Surveille le presse-papier : des que le bouton " Exporter JSON " du calculateur y depose un
# devis, la fiche Notion correspondante est remplie. Samuel n'a donc qu'un seul geste a faire.
#
# Lancement :  powershell -Sta -ExecutionPolicy Bypass -File "<vault>\.claude\scripts\watch-devis-export.ps1"
# Arret     :  fermer la fenetre (ou Ctrl+C).
#
# NB encodage : fichier volontairement sans caractere accentue litteral. PowerShell 5.1 lit les
# .ps1 sans BOM avec l'encodage systeme, ce qui corrompait "Demenage" -> chemin introuvable.
# Le nom accentue est reconstruit via [char]. Meme convention que watch-clippings.ps1.
#
# NB pourquoi le presse-papier : l'artefact publie tourne sous une CSP qui bloque tout
# fetch/XHR vers un autre hote - il ne PEUT PAS appeler un serveur local. Le presse-papier est
# le seul canal entre la page et le poste. C'est aussi le seul geste deja fait par l'humain.
#
# Le contrat samdem.groupage.valide/1 (planificateur de groupage) n'est plus traite ici depuis le
# 11/09/2026 : le workflow groupage est autonome et a son propre veilleur,
# outils\Groupage\veille_groupage.ps1. Ne pas remettre de branche groupage dans ce fichier : les
# deux veilleurs lanceraient crm_groupage.py en double.
#
# NB -Sta : Get-Clipboard exige un thread STA. Sans -Sta, la lecture renvoie du vide en boucle.
#
# NB idempotence : on retient l'empreinte SHA1 des exports deja traites (dans le fichier
# .devis-exports-vus). Reappuyer sur " Exporter JSON " sans rien changer ne reecrit pas la fiche ;
# modifier une valeur puis reexporter produit une empreinte differente, donc un nouveau
# traitement. Le presse-papier peut etre relu des dizaines de fois entre deux clics.

# NB encodage (2) : sans ces deux lignes, PowerShell decode la sortie de Python dans la page de
# codes de la console et le journal se remplit de " Oe? " la ou Python a ecrit un symbole euro.
# Le script Python ecrit deja en UTF-8 : il faut le dire a PowerShell.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$e = [char]0x00E9
$Vault    = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Script   = Join-Path $Vault "outils\pipeline\finalisation.py"
$Sorties  = Join-Path $Vault "donnees\Devis g${e}n${e}r${e}s\exports"
New-Item -ItemType Directory -Force -Path $Sorties | Out-Null
$LogFile  = Join-Path $Vault ".claude\scripts\devis-export.log"
$VusFile  = Join-Path $Vault ".claude\scripts\.devis-exports-vus"
$Python   = "python"
$Interval = 2       # secondes entre deux lectures du presse-papier

function Write-Log {
    param($Msg, $Couleur = "Gray")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$ts] $Msg" -Encoding UTF8
    Write-Host "[$ts] $Msg" -ForegroundColor $Couleur
}

function Notifier {
    param($Titre, $Msg)
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $n = New-Object System.Windows.Forms.NotifyIcon
        $n.Icon = [System.Drawing.SystemIcons]::Information
        $n.BalloonTipTitle = $Titre
        $n.BalloonTipText  = $Msg
        $n.Visible = $true
        $n.ShowBalloonTip(6000)
        Start-Sleep -Milliseconds 300
    } catch { }   # une notification qui echoue ne doit jamais arreter la boucle
}

function Empreinte {
    param($Texte)
    $sha = [System.Security.Cryptography.SHA1]::Create()
    $b = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Texte))
    return [System.BitConverter]::ToString($b).Replace("-", "")
}

if (-not (Test-Path $Script))  { Write-Log "ERREUR : $Script introuvable - arret." "Red"; exit 1 }
if (-not (Test-Path $Sorties)) { New-Item -ItemType Directory -Path $Sorties -Force | Out-Null }
if (-not (Test-Path $VusFile)) { New-Item -ItemType File -Path $VusFile -Force | Out-Null }

# Instance unique : le lanceur du dossier Demarrage et un lancement a la main peuvent
# coexister. Deux veilleurs ne cassent rien (l'empreinte des exports deja traites protege la
# fiche) mais doublent les appels ; on s'arrete plutot que de travailler en double.
$mutex = New-Object System.Threading.Mutex($false, "Global\SamDemDevisWatcher")
if (-not $mutex.WaitOne(0)) {
    Write-Log "Un veilleur tourne deja - ce lancement s'arrete." "Yellow"
    exit 0
}

Write-Log "Surveillance du presse-papier demarree. Exporter JSON remplira la fiche Notion." "Cyan"
Write-Log "Journal : $LogFile"

$dernier = ""
while ($true) {
    Start-Sleep -Seconds $Interval
    $txt = ""
    try { $txt = Get-Clipboard -Raw -ErrorAction SilentlyContinue } catch { }
    if ([string]::IsNullOrWhiteSpace($txt)) { continue }
    if ($txt -eq $dernier) { continue }
    $dernier = $txt

    if ($txt -notlike '*samdem.devis.export/1*') { continue }

    $emp = Empreinte $txt
    if (Select-String -Path $VusFile -SimpleMatch -Pattern $emp -Quiet) {
        Write-Log "Export deja traite (empreinte $($emp.Substring(0,8))) - ignore."
        continue
    }

    # Nom du client, pour un fichier lisible dans Devis generes\exports
    $client = "devis"
    try {
        $o = $txt | ConvertFrom-Json
        if ($o.client) { $client = $o.client }
        if ($o.fiche -and $o.fiche.titre) { $client = $o.fiche.titre }
    } catch {
        Write-Log "JSON illisible dans le presse-papier - ignore." "Yellow"
        continue
    }
    $client = ($client -replace '[\\/:*?"<>|]', '-').Trim()
    $fichier = Join-Path $Sorties ((Get-Date -Format "yyyyMMdd-HHmmss") + " " + $client + ".json")
    [System.IO.File]::WriteAllText($fichier, $txt, (New-Object System.Text.UTF8Encoding($false)))

    Write-Log "Export recu : $client -> finalisation de la fiche Notion..." "Cyan"
    # --whatsapp est sans effet tant que BEEPER_ACCESS_TOKEN et SAMDEM_WHATSAPP_CHAT ne
    # sont pas renseignes dans .env : le message part alors en file d'attente.
    $sortie = & $Python $Script $fichier --appliquer --whatsapp 2>&1
    $code = $LASTEXITCODE
    $sortie | ForEach-Object { Add-Content -Path $LogFile -Value "    $_" -Encoding UTF8 }

    switch ($code) {
        0 {
            Add-Content -Path $VusFile -Value $emp
            Write-Log "OK - fiche $client mise a jour." "Green"
            Notifier "Fiche remplie" "$client - bloc de chiffrage et proprietes mis a jour."
        }
        default {
            Write-Log "ECHEC (code $code) sur $client - voir le journal." "Red"
            Notifier "Echec" "$client - la fiche n'a pas ete mise a jour. Voir devis-export.log."
        }
    }
    $sortie | Select-Object -Last 6 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
}
