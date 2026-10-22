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
# Replace the code cleanly so files deleted from the repo don't linger on the server:
# backend/ is swapped for the fresh copy; in deploy/ every file except .env is removed unless the
# upload has it, then the upload is copied over (cp keeps the inodes of bind-mounted configs).
# Storage, MySQL and Redis live in Docker volumes, not in these folders.
$remote = @(
    'set -e'
    'mkdir -p ~/mistake-book/deploy'
    'new=$(mktemp -d ~/mistake-book/.upload.XXXXXX)'
    'tar -xf /tmp/mistake-book-deploy.tar -C $new'
    'rm /tmp/mistake-book-deploy.tar'
    'rm -rf ~/mistake-book/backend'
    'mv $new/backend ~/mistake-book/backend'
    'shopt -s nullglob dotglob'
    'for f in ~/mistake-book/deploy/*; do b=$(basename $f); [ $b = .env ] || [ -e $new/deploy/$b ] || rm -rf $f; done'
    'cp -r $new/deploy/. ~/mistake-book/deploy/'
    'rm -rf $new'
    'bash ~/mistake-book/deploy/remote.sh'
) -join '; '
ssh @ssh $Server $remote
if ($LASTEXITCODE -ne 0) { throw "deploy failed (exit $LASTEXITCODE)" }
Write-Host "deployed $rev"
