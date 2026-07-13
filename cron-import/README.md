# agenda-import-cron

A standalone Railway service whose only job is to call `POST /bulk-import/start`
on the live `fw-fiscal-analyzer` app once a day, so newly posted Fort Worth
Council agendas get pulled in automatically instead of requiring someone to
click "Import."

This is intentionally isolated from the main app (own Dockerfile, own
`railway.json`) so it can't affect the running web service.

## Railway setup (one-time)

This service was added to the `fw-fiscal-analyzer` Railway project via:

```
railway add --repo ellacggroup/fw-fiscal-analyzer --service agenda-import-cron
```

Two settings need to be set in the Railway dashboard for this service
(not available via CLI):

1. **Settings → Source → Root Directory** → `cron-import`
   (so Railway builds this folder's Dockerfile, not the repo root one)
2. **Variables** → add `TARGET_URL` = `https://fw-fiscal-analyzer-production-b998.up.railway.app`

Once those are set, Railway reads `deploy.cronSchedule` from this folder's
`railway.json` (`0 8 * * *` = 08:00 UTC daily) and runs the container on
that schedule. Each run just does one `curl` call and exits.

## Changing the schedule

Edit `cronSchedule` in `railway.json` (standard 5-field cron syntax, UTC).
