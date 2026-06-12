# close-the-windows

Compares the **outdoor** temperature (a [Weather Underground](https://www.wunderground.com/)
personal weather station) against the **indoor** temperature (a [Shelly H&T Gen3](https://kb.shelly.cloud/knowledge-base/shelly-h-t-gen3)
read over the Shelly Cloud API) and sends a [Pushover](https://pushover.net/) push
when the relationship flips — so you can keep the house as cool as possible:

- outdoor drops **below** indoor → **"open the windows"** (pull the cool air in)
- outdoor rises **above** indoor → **"close the windows"** (keep the cool in)

It also logs every reading (both temps + both humidities) to two files: `data.json`
(a rolling 24 h window, read by the companion
**[close-the-windows-dashboard](https://github.com/prosciutto-crudo/close-the-windows-dashboard)**
to render its chart) and `history.csv` (a never-trimmed archive that grows
indefinitely, for day-over-day analysis). Runs entirely in the cloud via GitHub
Actions. Nothing runs locally.

## How it works

- `monitor.py` (stdlib only — no dependencies) reads the outdoor temp + humidity from
  the WU PWS API and the indoor temp + humidity from the Shelly Cloud API
  (`/device/status?id=…&auth_key=…`; temp at `data.device_status["temperature:0"].tC`,
  humidity at `["humidity:0"].rh`). The WU request passes `numericPrecision=decimal`
  so the outdoor temp comes back at 0.1 °C resolution (e.g. `14.8`) instead of whole
  degrees — matching what the station page shows.
- It notifies **only on a flip** (open↔close), never on every poll. A **hysteresis
  margin** (`MARGIN_C`, default 1 °C) is the deadband: the recommendation only changes
  once outdoor clears indoor by that margin, so it won't flap when the two are close.
- **Quiet hours 22:00–06:00 Europe/Madrid** (`QUIET_HOURS`) suppress only *pushes* —
  data is still logged round the clock. A separate `notified_state` means the first
  run after quiet hours sends one catch-up push if the recommendation flipped overnight.
- A **staleness guard** (`MAX_STALE_MIN`, default 90) and an offline check stop a dead
  or sleeping sensor from triggering a false flip.
- `data.json` holds `windows_open` (current recommendation), `notified_state`, and a
  rolling `points` array trimmed to `WINDOW_HOURS` (default 24) — the dashboard feed.
  `history.csv` gets one appended row per reading (`t,iso_madrid,out_t,in_t,out_h,in_h,windows_open`)
  and is never trimmed — the indefinite archive. The workflow commits both every run.
- `.github/workflows/monitor.yml` runs **every 5 min, 24/7** (cron `*/5 * * * *`). The
  repo is **public**, so Actions minutes are free. GitHub's `schedule` is best-effort and
  drops many `*/5` runs, so this native cron is only a backup — reliable cadence comes
  from a **[Val Town cron pinger](https://www.val.town/x/prosciuttocrudo/close-the-windows-pinger)**
  firing `workflow_dispatch` every 5 min. A `concurrency` group dedupes overlaps. The
  workflow also has a manual **Run workflow** button.

> The Shelly H&T sleeps on battery (reports only on a ≥0.5 °C change, or every 2 h).
> Keep it **USB-powered** so it reports every few minutes and the cloud value stays fresh.

## Configuration

Set these as repository **Actions secrets** (Settings → Secrets and variables → Actions):

| Secret | What it is |
|---|---|
| `WU_STATION_ID` | Weather Underground station ID (outdoor source), e.g. `ISANTC180` |
| `WU_API_KEY` | Weather Underground / weather.com API key |
| `SHELLY_SERVER` | Shelly Cloud host, e.g. `https://shelly-267-eu.shelly.cloud` |
| `SHELLY_DEVICE_ID` | Shelly device ID, e.g. `d885ac12b894` |
| `SHELLY_AUTH_KEY` | Shelly Cloud authorization key (app → User Settings → Authorization Cloud Key) |
| `PUSHOVER_USER` | Your Pushover user key |
| `PUSHOVER_TOKEN` | Your Pushover application API token |

Secrets stay encrypted even though the repo is public. `MARGIN_C` and `QUIET_HOURS`
are set in the workflow; `NIGHT_START`/`NIGHT_END`/`NOTIFY_ON_INIT`/`WINDOW_HOURS`/
`MAX_STALE_MIN`/`DATA_FILE`/`HISTORY_FILE` are optional overrides read by `monitor.py`.

## Run locally (optional)

```bash
WU_STATION_ID=... WU_API_KEY=... \
SHELLY_SERVER=... SHELLY_DEVICE_ID=... SHELLY_AUTH_KEY=... \
PUSHOVER_USER=... PUSHOVER_TOKEN=... \
  python3 monitor.py
```
