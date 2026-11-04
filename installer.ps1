# Installation de la chaine de devis. Fichier sans accent : PowerShell 5.1 lit les .ps1 sans BOM
# avec l'encodage systeme. Lance par installer.bat.
$ErrorActionPreference = "Stop"
$Racine = $PSScriptRoot
Set-Location $Racine

Write-Host ""
Write-Host "Installation de la chaine de devis dans $Racine" -ForegroundColor Cyan

if ($Racine -match "OneDrive|Google Drive") {
    Write-Host "Ce dossier est synchronise. Deplace-le dans C:\SamDem\pipeline-sam, puis relance." -ForegroundColor Red
    exit 1
}
$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python -or $Python.Source -match "WindowsApps") {
    Write-Host "Python est introuvable. Installe-le depuis python.org en cochant Add python.exe to PATH, puis relance." -ForegroundColor Red
    exit 1
}

Write-Host "1/4  Modules Python..."
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Host "Installation des modules impossible : verifie la connexion." -ForegroundColor Red; exit 1 }

Write-Host "2/4  Fichier .env..."
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env" }
foreach ($d in @(".claude\scripts", "donnees\Devis SamDem\specs", "donnees\Inventaires")) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

Write-Host "3/4  Veilleur au demarrage de Windows..."
$Veilleur = Join-Path $Racine "outils\pipeline\watch-devis-export.ps1"
$Demarrage = [Environment]::GetFolderPath("Startup")
$Lanceur = Join-Path $Demarrage "SamDemenage-DevisWatcher.bat"
$Contenu = "@echo off`r`nrem Veilleur du presse-papier : Exporter JSON lance la finalisation du devis.`r`nstart `"`" /min powershell.exe -Sta -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Veilleur`"`r`n"
[System.IO.File]::WriteAllText($Lanceur, $Contenu, (New-Object System.Text.ASCIIEncoding))

Write-Host "4/4  Lancement du veilleur..."
$Deja = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | Where-Object { $_.CommandLine -match "watch-devis-export" -and $_.ProcessId -ne $PID }
if (-not $Deja) { Start-Process -FilePath $Lanceur -WindowStyle Hidden }

Write-Host ""
Write-Host "Termine. Etat de l'installation :" -ForegroundColor Green
Start-Sleep -Seconds 3
python verifier_installation.py
Write-Host ""
Write-Host "Suite : ouvre ce dossier dans Claude Code, et suis guides\02-cle-hubspot.md" -ForegroundColor Cyan
