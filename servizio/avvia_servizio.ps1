# Avvia il servizio filtro-pii nascosto (nessuna finestra), se non e' gia' in ascolto.
# Uso: powershell -NoProfile -ExecutionPolicy Bypass -File avvia_servizio.ps1 [-Porta 5117]
#
# Quale Python usa, nell'ordine:
#   1. la variabile d'ambiente FILTRO_PII_PYTHON (percorso di pythonw.exe o pyw.exe);
#   2. l'ambiente creato da installa.ps1: %LOCALAPPDATA%\claude-filtro-pii\venv;
#   3. il launcher di Python (pyw) o pythonw trovati nel sistema.
param([int]$Porta = 5117)

$qui = Split-Path -Parent $MyInvocation.MyCommand.Path
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Porta/stato" -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) { Write-Output "gia' attivo"; exit 0 }
} catch { }

$candidati = @()
if ($env:FILTRO_PII_PYTHON) { $candidati += $env:FILTRO_PII_PYTHON }
$candidati += (Join-Path $env:LOCALAPPDATA "claude-filtro-pii\venv\Scripts\pythonw.exe")
$candidati += (Join-Path $env:LOCALAPPDATA "Programs\Python\Launcher\pyw.exe")
$python = $candidati | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
    foreach ($nome in "pyw", "pythonw") {
        $comando = Get-Command $nome -ErrorAction SilentlyContinue
        if ($comando) { $python = $comando.Source; break }
    }
}
if (-not $python) {
    Write-Output "Python non trovato: esegui installa.ps1 oppure imposta FILTRO_PII_PYTHON"
    exit 1
}

# Il percorso va tra virgolette: Start-Process non le aggiunge da solo.
$script = '"' + (Join-Path $qui "servizio.py") + '"'
Start-Process -FilePath $python -ArgumentList @($script, "--porta", "$Porta") -WindowStyle Hidden -WorkingDirectory $qui
Write-Output "avviato"
