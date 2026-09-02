# Hibernated 2026-09-02

This project is **wound down for the season**. Nothing polls, notifies, commits
or deploys any more. The code and all the data are intact — this file is the
runbook for putting it back in the air (the plan is next summer).

The last logged reading is the final row of `history.csv`
(`2026-09-02`, ~11:40 Madrid). `data.json` is frozen at that same moment.

## What was switched off, and how

| Piece | What was done | Where |
|---|---|---|
| Actions cron (5-min poll) | `schedule:` block **removed** from the workflow; `workflow_dispatch` kept, so the manual **Run workflow** button still works | `.github/workflows/monitor.yml` |
| Val Town pinger | `main.ts` file type flipped **`interval` → `script`**, which is what stops a cron val firing. Cron expression (`*/5 * * * *`) and the `GH_PAT` env var left as they were | [val](https://www.val.town/x/prosciuttocrudo/close-the-windows-pinger) |
| GitHub PAT | **Revoked** — do not expect the pinger to work until a new one is minted | GitHub → Settings → Developer settings → Tokens |
| Vercel dashboard | **Paused** — serves `503 DEPLOYMENT_PAUSED`. Project, URL, `FANLOG_SECRET` env var and the GitHub auto-deploy link all kept | project `prj_7x0SoW7IqjZWnQPDbmF4qG3h2H2X` |
| Val Town fanlog | **Left live and untouched** (a public HTTP + SQLite val). Its 2 rows are also archived to `archive/fan-log.csv` | [val](https://www.val.town/x/prosciuttocrudo/close-the-windows-fanlog) |
| Repo Actions secrets | **Left in place** (encrypted, and inert with no cron). `WU_API_KEY` is the one most likely to have gone stale by next summer | repo → Settings → Secrets |
| Shelly H&T Gen3 | **No action taken.** It's still USB-powered and still reporting to Shelly Cloud; nothing reads it. Safe to unplug — but see the note below before you do | physical, at home |

## Re-spinning next summer

1. **Mint a new fine-grained GitHub PAT** — Actions **read+write** on
   `prosciutto-crudo/close-the-windows`, nothing else. Set it as the `GH_PAT`
   env var on the pinger val. (The old one was revoked; this is why the pinger
   won't work until you do this.)
2. **Re-arm the pinger val** — flip `main.ts` back from `script` to
   `interval`. Confirm the cron still reads `*/5 * * * *`. Source is also in
   `archive/pinger-main.ts` if the val itself is gone.
3. **Restore the native cron** — uncomment the `schedule:` block in
   `.github/workflows/monitor.yml` (it's the documented backup; the pinger is
   what actually delivers reliable cadence).
4. **Unpause Vercel** — the project keeps its URL and env vars, so this is the
   only step needed for <https://close-the-windows-dashboard.vercel.app>.
5. **Check the Shelly is USB-powered** and reporting fresh values. On battery it
   sleeps and only reports on a ≥0.5 °C change or every 2 h, which trips
   `monitor.py`'s staleness guard (`MAX_STALE_MIN`, default 90).
6. **Re-verify the secrets** — `WU_API_KEY` / `WU_STATION_ID` especially. A
   dead WU key fails the run loudly, which is the good case; a *stale station*
   returns old readings, which is the bad case.
7. **Sanity-run it** — hit **Run workflow** manually once and check that a
   `Log reading` commit lands before trusting the notifications again.

### Two things that will bite you

- **`NOTIFY_ON_INIT: "on"`** is set in the workflow. The first run after
  hibernation will fire a Pushover push for the *current* recommendation, not a
  genuine flip. That's expected, not a bug.
- **There will be a months-wide gap in the data.** `history.csv` jumps from
  September to whenever you restart. Anything doing day-over-day analysis needs
  to handle the discontinuity — and the dashboard's 4-day overlay will look
  broken until 96 h of fresh readings have accumulated.

## The data

- `history.csv` — the archive, **9,288 readings** from `2026-06-12 05:55` to
  `2026-09-02 11:40` Madrid. Never trimmed. This is the irreplaceable artifact.
- `data.json` — the rolling 96 h window the dashboard reads. Frozen.
- `archive/fan-log.csv` — the hand-entered overnight-fan log, exported from the
  fanlog val's SQLite (it existed nowhere else).
