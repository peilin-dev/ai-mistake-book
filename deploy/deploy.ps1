# One-command deploy from this computer: upload the committed backend + deploy files, build and restart.
# Usage: powershell -File deploy\deploy.ps1   (optional: -Server ubuntu@1.2.3.4 -Key path\to\key)
param(
    [string]$Server = 'ubuntu@42.194.206.186',
    [string]$Key = "$env:USERPROFILE\.ssh\ai_mistake_book_server.pem",
    [switch]$DryRun   # build and package only: print the tar path, skip scp/ssh
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$tar = Join-Path $env:TEMP 'mistake-book-deploy.tar'
$stage = Join-Path $env:TEMP 'mistake-book-stage'

Push-Location $repo
try {
    if (git status --porcelain backend deploy) { Write-Warning 'backend/ or deploy/ has uncommitted changes; only committed code is deployed.' }
    if (git status --porcelain web) { Write-Warning 'web/ has uncommitted changes; the web build uses the working tree.' }

    # Build the web admin (stop on any failure).
    Push-Location (Join-Path $repo 'web')
    try {
        npm ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed (exit $LASTEXITCODE)" }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build failed (exit $LASTEXITCODE)" }
    } finally { Pop-Location }
    if (-not (Test-Path (Join-Path $repo 'web\dist\index.html'))) { throw 'web/dist/index.html missing after build' }

    # Package: committed backend + deploy, plus the built web files under deploy/web.
    git archive --format=tar -o $tar HEAD backend deploy
    if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }
    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
    New-Item -ItemType Directory -Path $stage | Out-Null
    tar -xf $tar -C $stage
    if ($LASTEXITCODE -ne 0) { throw 'tar extract failed' }
    $webOut = Join-Path $stage 'deploy\web'
    if (Test-Path $webOut) { Remove-Item -Recurse -Force $webOut }
    New-Item -ItemType Directory -Path $webOut | Out-Null
    Copy-Item -Path (Join-Path $repo 'web\dist\*') -Destination $webOut -Recurse
    Remove-Item -Force $tar
    tar -cf $tar -C $stage backend deploy
    if ($LASTEXITCODE -ne 0) { throw 'tar create failed' }
    Remove-Item -Recurse -Force $stage
    $rev = git rev-parse --short HEAD
} finally { Pop-Location }

if ($DryRun) {
    Write-Host "dry run: packaged $rev at $tar (nothing uploaded)"
    return
}

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
    # remote.sh prunes stale deploy/web files (using $new), checks nginx.conf, deploys, and removes $new on exit.
    'bash ~/mistake-book/deploy/remote.sh $new'
) -join '; '
ssh @ssh $Server $remote
if ($LASTEXITCODE -ne 0) { throw "deploy failed (exit $LASTEXITCODE)" }
Write-Host "deployed $rev"
