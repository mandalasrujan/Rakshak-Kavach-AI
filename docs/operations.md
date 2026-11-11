# Operations runbook

## Backup and restore (verified 2026-11-11)

PostgreSQL holds everything except the uploaded PDFs: patients, consent, documents, chunks with vectors, lab results, medications, chats and checkpoints, snapshots, shares and the audit log. Back up the database and the `storage` volume together.

```bash
# Backup (Docker Compose)
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > rakshak-$(date +%F).dump
docker run --rm -v rakshak-kavach-ai_storage:/data -v "$PWD":/backup alpine tar czf /backup/storage-$(date +%F).tgz -C /data .

# Restore into a fresh database, then re-run the app-role bootstrap
docker compose exec -T postgres createdb -U "$POSTGRES_USER" rakshak_restore
docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d rakshak_restore --no-owner < rakshak-YYYY-MM-DD.dump
docker compose run --rm -e MIGRATION_DATABASE_URL=... migrate python -m app.db.app_role
```

Drill result in the build environment (`pg_dump -Fc`, then `pg_restore` into a new database, 216 KB dump):
- Row counts matched for every table (patients 5, documents 13, chunks 68 with 68 vectors, lab results 51, medications 8, snapshots 4, shares 4, doctor sessions 2, audit log 4,961).
- All 13 `patient_isolation` RLS policies and the `audit_log_append_only` trigger were restored.

**Deleted data and backups:** a document deleted under M12 still exists in older backups until they rotate. Keep backup retention short and encrypt backups.

Redis holds only the job queue and rate-limit counters. With `appendonly yes` (as in Compose), queued jobs survive restarts. A lost queue only delays processing: re-uploading a failed document re-queues it.

## Restart persistence (verified 2026-11-11)

1. A document was uploaded while the worker was stopped, leaving 1 job in Redis.
2. PostgreSQL (`pg_ctl restart`) and Redis (append-only file) were both restarted.
3. The API and worker were then started again.

Result: login worked, consent was still granted, the queued job survived (1 → 1), and the worker processed the document to `ready` with 3 lab results.

## Logs

The API, worker and nginx write structured logs with IDs, codes and timings only. Request bodies, query strings, emails, tokens, PINs and document content are never logged; tests enforce this. nginx logs the method and path only.

## Rate limits

| Limit | Default | Setting |
|---|---|---|
| Login | 5 per email and 20 per IP per 15 min | `LOGIN_*` |
| Registration | 10 per IP per hour | `REGISTER_*` |
| `/ask` and chat messages | 60 per patient per hour | `ASK_MAX_PER_HOUR` |
| Doctor PIN exchange | 20 per IP per 15 min, plus a permanent lock after 5 wrong PINs per share | `SHARE_EXCHANGE_*`, `SHARE_PIN_MAX_ATTEMPTS` |

Behind nginx, client IPs come from `X-Forwarded-For`, which nginx overwrites (it does not append), so clients cannot spoof it.
