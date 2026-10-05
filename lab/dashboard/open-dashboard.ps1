[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)] [int] $Port = 8787,
    [switch] $NoBrowser,
    [switch] $Lan,
    [string] $LanAddress
)
$ErrorActionPreference = 'Stop'
$dashboardUrl = "http://127.0.0.1:$Port"
$dashboardRoot = Join-Path $env:USERPROFILE '.codex-lab/dashboard'
New-Item -ItemType Directory -Path $dashboardRoot -Force | Out-Null
try {
    $existing = Invoke-RestMethod "$dashboardUrl/api/campaigns" -TimeoutSec 2
} catch { $existing = $null }
if ($null -eq $existing -or $null -eq $existing.campaigns) {
    $serverPath = Join-Path $PSScriptRoot 'server.py'
    $linuxServer = (& wsl.exe -d Ubuntu --exec wslpath -a $serverPath).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the dashboard path in Ubuntu.' }
    $dashboardProcess = Start-Process -FilePath 'wsl.exe' -ArgumentList @(
        '-d', 'Ubuntu', '--exec', 'python3', ('"' + $linuxServer + '"'), '--port', $Port
    ) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $dashboardRoot "server-$Port.stdout.log") -RedirectStandardError (Join-Path $dashboardRoot "server-$Port.stderr.log")
    $dashboardProcess.Id | Set-Content (Join-Path $dashboardRoot "server-$Port.pid")
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 300
        try {
            $snapshot = Invoke-RestMethod "$dashboardUrl/api/campaigns" -TimeoutSec 2
            if ($null -ne $snapshot.campaigns) { $ready = $true; break }
        } catch { }
        if ($dashboardProcess.HasExited) { break }
    }
    if (-not $ready) { throw "Dashboard did not start. See $dashboardRoot/server-$Port.stderr.log" }
}
if ($Lan -or $LanAddress) {
    $localAddresses = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
        $_.AddressState -eq 'Preferred' -and $_.IPAddress -notmatch '^(127\.|169\.254\.)'
    })
    if ($LanAddress) {
        $address = $localAddresses | Where-Object IPAddress -eq $LanAddress | Select-Object -First 1
    } else {
        $gatewayInterfaces = @(Get-NetIPConfiguration | Where-Object IPv4DefaultGateway | Select-Object -ExpandProperty InterfaceIndex)
        $address = $localAddresses | Where-Object { $_.InterfaceIndex -in $gatewayInterfaces } | Select-Object -First 1
    }
    if (-not $address) { throw 'No connected LAN address found. Specify -LanAddress with this PC''s local IPv4 address.' }
    $dashboardUrl = "http://$($address.IPAddress):$Port"
    try {
        $lanSnapshot = Invoke-RestMethod "$dashboardUrl/api/campaigns" -TimeoutSec 2
    } catch { $lanSnapshot = $null }
    if ($null -eq $lanSnapshot -or $null -eq $lanSnapshot.campaigns) {
        $pythonPath = (Get-Command python.exe -ErrorAction Stop).Source
        $proxyPath = Join-Path $PSScriptRoot 'lan_proxy.py'
        $proxyProcess = Start-Process -FilePath $pythonPath -ArgumentList @(
            ('"' + $proxyPath + '"'), '--listen-address', $address.IPAddress,
            '--subnet', "$($address.IPAddress)/$($address.PrefixLength)",
            '--port', $Port, '--upstream-port', $Port
        ) -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $dashboardRoot "lan-$Port.stdout.log") -RedirectStandardError (Join-Path $dashboardRoot "lan-$Port.stderr.log")
        $proxyProcess.Id | Set-Content (Join-Path $dashboardRoot "lan-$Port.pid")
        $lanReady = $false
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            Start-Sleep -Milliseconds 300
            try {
                $lanSnapshot = Invoke-RestMethod "$dashboardUrl/api/campaigns" -TimeoutSec 2
                if ($null -ne $lanSnapshot.campaigns) { $lanReady = $true; break }
            } catch { }
            if ($proxyProcess.HasExited) { break }
        }
        if (-not $lanReady) { throw "LAN dashboard did not start. See $dashboardRoot/lan-$Port.stderr.log" }
    }
    Write-Output 'LAN access is limited to clients on the selected local subnet.'
}
Write-Output "Read-only dashboard: $dashboardUrl"
if (-not $NoBrowser) { Start-Process $dashboardUrl }
