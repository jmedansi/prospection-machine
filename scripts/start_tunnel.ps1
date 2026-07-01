# start_tunnel.ps1 — Démarre le tunnel Cloudflare avec route bypass VPN
# Exécuter au démarrage Windows (tâche planifiée) ou manuellement

$ErrorActionPreference = "SilentlyContinue"

# --- 1. Route réseau pour contourner le VPN ---
$cloudflareRoute = Get-NetRoute -DestinationPrefix "198.41.0.0/16" -ErrorAction SilentlyContinue
if (-not $cloudflareRoute) {
    Write-Host "[TUNNEL] Ajout de la route 198.41.0.0/16 -> 192.168.1.1 (bypass VPN)..."
    New-NetRoute -DestinationPrefix "198.41.0.0/16" -NextHop "192.168.1.1" -InterfaceIndex 18 -RouteMetric 10
} else {
    Write-Host "[TUNNEL] Route Cloudflare deja en place."
}

# --- 2. Tuer les anciens processus cloudflared ---
$existing = Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[TUNNEL] Arret de $($existing.Count) ancien(s) processus cloudflared..."
    $existing | Stop-Process -Force
    Start-Sleep -Seconds 2
}

# --- 3. Lancer cloudflared en background ---
Write-Host "[TUNNEL] Demarrage de cloudflared (protocol http2)..."
$cloudflaredPath = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cloudflaredPath) {
    Write-Host "[TUNNEL] ERREUR: cloudflared introuvable dans le PATH."
    exit 1
}

Start-Process -FilePath $cloudflaredPath -ArgumentList "tunnel", "--no-autoupdate", "--protocol", "http2", "run", "facebook-webhook" -WindowStyle Hidden

# --- 4. Vérifier la connexion (attente 10s) ---
Write-Host "[TUNNEL] Verification de la connexion..."
Start-Sleep -Seconds 10

$info = & cloudflared tunnel info facebook-webhook 2>&1
if ($info -match "CONNECTOR ID") {
    Write-Host "[TUNNEL] OK - Tunnel connecte a Cloudflare."
} else {
    Write-Host "[TUNNEL] ATTENTION - Le tunnel semble ne pas etre connecte. Verifiez les logs."
}
