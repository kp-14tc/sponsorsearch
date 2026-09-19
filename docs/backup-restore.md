# Backup and restore

Back up PostgreSQL, n8n's volume, and .env (especially `N8N_ENCRYPTION_KEY`). PostgreSQL contains both lead data and n8n's database. The key is needed to decrypt saved n8n credentials. Backups include private research/contact data and secrets; keep them encrypted/off Git and copy them off the Windows disk.

These commands run from the repository root in PowerShell. They stop writers during the snapshot and keep binary output out of PowerShell redirection, which can corrupt archives on older PowerShell versions.

```powershell
New-Item -ItemType Directory -Force backups | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$dbBackup = "backups/postgres-$stamp.dump"
$n8nBackup = "backups/n8n-$stamp.tgz"
docker compose stop n8n worker
docker compose exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/frc-backup.dump'
if ($LASTEXITCODE -ne 0) { throw 'Database backup failed' }
docker compose cp postgres:/tmp/frc-backup.dump $dbBackup
docker compose run --name frc-n8n-backup --no-deps --user root --entrypoint sh n8n -c 'tar -czf /tmp/n8n-backup.tgz -C /home/node .n8n'
if ($LASTEXITCODE -ne 0) { throw 'n8n archive failed' }
docker cp frc-n8n-backup:/tmp/n8n-backup.tgz $n8nBackup
docker rm frc-n8n-backup
Copy-Item .env "backups/env-$stamp.private"
docker compose start n8n worker
```

Check every Docker exit code; if a command fails, stop and retain earlier backups. If the named helper container already exists from a failed attempt, inspect/remove that helper before retrying. The .env copy is plaintext: protect or encrypt the backup directory. SearXNG cache and downloaded models can be rebuilt and are not part of this snapshot.

## Restore rehearsal

Restoration replaces data. Rehearse on a separate Windows/Docker test installation first, with the same repository/image versions. The fixed Compose project name and localhost ports mean you must not start a second copy alongside the live stack unchanged. Never delete the live volumes to test a restore.

On that separate installation, copy the saved .env into place, start only PostgreSQL and initialize the empty schema, then restore the chosen database archive:

```powershell
docker compose up -d postgres
docker compose cp backups/postgres-CHOSEN.dump postgres:/tmp/frc-restore.dump
docker compose exec -T postgres sh -c 'pg_restore --clean --if-exists --no-owner --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/frc-restore.dump'
```

For n8n, create its container/volume without starting the editor, copy the archive, and extract it with a temporary container sharing that volume:

```powershell
docker compose create n8n
docker compose run -d --name frc-n8n-restore --no-deps --user root --entrypoint sh n8n -c 'sleep 600'
```

Then copy and extract the archive:

```powershell
docker cp backups/n8n-CHOSEN.tgz frc-n8n-restore:/tmp/n8n-restore.tgz
docker exec frc-n8n-restore sh -c 'tar -xzf /tmp/n8n-restore.tgz -C /home/node && chown -R node:node /home/node/.n8n'
docker stop frc-n8n-restore
docker rm frc-n8n-restore
docker compose up -d --build
```

Use the original encryption key. Verify owner login, imported workflows/credentials, lead/evidence/contact counts and a reviewed draft. Run health checks before resuming discovery. Test the backup and restore procedure in a disposable environment before relying on it.
