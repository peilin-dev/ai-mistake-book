# One-command deploy from this computer: upload the committed backend + deploy files, build and restart.
# Usage: powershell -File deploy\deploy.ps1   (optional: -Server ubuntu@1.2.3.4 -Key path\to\key)
param(
    [string]$Server = 'ubuntu@42.194.206.186',
    [string]$Key = "$env:USERPROFILE\.ssh\ai_mistake_book_server.pem"
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$tar = Join-Path $env:TEMP 'mistake-book-deploy.tar'

Push-Location $repo
try {
    if (git status --porcelain backend deploy) { Write-Warning 'backend/ or deploy/ has uncommitted changes; only committed code is deployed.' }
    git archive --format=tar -o $tar HEAD backend deploy
    $rev = git rev-parse --short HEAD
} finally { Pop-Location }

$ssh = @('-i', $Key, '-o', 'BatchMode=yes')
Write-Host "uploading $rev"
scp @ssh $tar "${Server}:/tmp/mistake-book-deploy.tar"
# Keep the server's deploy/.env; replace everything else.
ssh @ssh $Server 'mkdir -p ~/mistake-book && tar -xf /tmp/mistake-book-deploy.tar -C ~/mistake-book && rm /tmp/mistake-book-deploy.tar && bash ~/mistake-book/deploy/remote.sh'
if ($LASTEXITCODE -ne 0) { throw "deploy failed (exit $LASTEXITCODE)" }
Write-Host "deployed $rev"
