# Prepara il motore Python del filtro-pii: ambiente virtuale, librerie, modello
# italiano di spaCy, test. Non installa la mod in Claude Code (vedi README).
#
# Uso (da PowerShell, nella cartella del repository):
#   powershell -ExecutionPolicy Bypass -File installa.ps1
#   powershell -ExecutionPolicy Bypass -File installa.ps1 -Python "C:\percorso\python.exe"
#
# Crea %LOCALAPPDATA%\claude-filtro-pii\venv (circa 1,5 GB con il modello).
param([string]$Python = "")

$qui = Split-Path -Parent $MyInvocation.MyCommand.Path
$base = Join-Path $env:LOCALAPPDATA "claude-filtro-pii"
$venv = Join-Path $base "venv"
$vpy = Join-Path $venv "Scripts\python.exe"

function Esegui-Passo([string]$Titolo, [scriptblock]$Comando) {
    Write-Host ""
    Write-Host "== $Titolo"
    & $Comando
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERRORE nel passo: $Titolo (codice $LASTEXITCODE)"
        exit 1
    }
}

if (-not $Python) {
    if (Get-Command py -ErrorAction SilentlyContinue) { $Python = "py" }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { $Python = "python" }
    else { Write-Host "Python non trovato: installalo da https://www.python.org/downloads/ (3.10 o successivo)"; exit 1 }
}

if (-not (Test-Path $vpy)) {
    Esegui-Passo "Creo l'ambiente virtuale in $venv" { & $Python -m venv $venv }
}
Esegui-Passo "Aggiorno pip" { & $vpy -m pip install --upgrade pip --quiet }
Esegui-Passo "Installo le librerie" { & $vpy -m pip install -r (Join-Path $qui "servizio\requirements.txt") }
Esegui-Passo "Scarico il modello italiano di spaCy (circa 570 MB)" { & $vpy -m spacy download it_core_news_lg }
Esegui-Passo "Eseguo i test del motore" { & $vpy -m unittest discover -s (Join-Path $qui "servizio") -p "test_motore.py" }

Write-Host ""
Write-Host "Motore pronto. Ora installa la mod in Claude Code (vedi README, sezione Installazione)."
