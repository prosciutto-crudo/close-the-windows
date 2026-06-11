# close-the-windows

Compares the **outdoor** temperature (a [Weather Underground](https://www.wunderground.com/)
personal weather station) against the **indoor** temperature (a [Shelly H&T Gen3](https://kb.shelly.cloud/knowledge-base/shelly-h-t-gen3)
read over the Shelly Cloud API) and sends a [Pushover](https://pushover.net/) push
when the relationship flips — so you can keep the house as cool as possible:

- outdoor drops **below** indoor → **"open the windows"** (pull the cool air in)
- outdoor rises **above** indoor → **"close the windows"** (keep the cool in)

It also logs every reading (both temps + both humidities) to `data.json`, which the
companion **[close-the-windows-dashboard](https://github.com/prosciutto-crudo/close-the-windows-dashboard)**
reads to render a rolling 24 h chart. Runs entirely in the cloud via GitHub Actions.
Nothing runs locally.

## How it works

- `monitor.py` (stdlib only — no dependencies) reads the outdoor temp + humidity from
  the WU PWS API and the indoor temp + humidity from the Shelly Cloud API
  (`/device/status?id=…&auth_key=…`; temp at `data.device_status["temperature:0"].tC`,
  humidity at `["humidity:0"].rh`).
- It notifies **only on a flip** (open↔close), never on every poll. A **hysteresis
  margin** (`MARGIN_C`, default 1 °C) is the deadband: the recommendation only changes
  once outdoor clears indoor by that margin, so it won't flap when the two are close.
- **Quiet hours 22:00–06:00 Europe/Madrid** (`QUIET_HOURS`) suppress only *pushes* —
  data is still logged round the clock. A separate `notified_state` means the first
  run after quiet hours sends one catch-up push if the recommendation flipped overnight.
- A **staleness guard** (`MAX_STALE_MIN`, default 90) and an offline check stop a dead
  or sleeping sensor from triggering a false flip.
- `data.json` holds `windows_open` (current recommendation), `notified_state`, and a
  rolling `points` array trimmed to `WINDOW_HOURS` (default 24). The workflow commits
  it every run — that's the data feed for the dashboard.
- `.github/workflows/monitor.yml` runs **every 10 min, 24/7** (cron `*/10 * * * *`). The
  repo is **public**, so Actions minutes are free. Note GitHub's `schedule` is
  best-effort — runs are often delayed/dropped, so the real cadence is irregular; data
  integrity is unaffected. The workflow has a manual **Run workflow** button.

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
`MAX_STALE_MIN` are optional overrides read by `monitor.py`.

## Run locally (optional)

```bash
WU_STATION_ID=... WU_API_KEY=... \
SHELLY_SERVER=... SHELLY_DEVICE_ID=... SHELLY_AUTH_KEY=... \
PUSHOVER_USER=... PUSHOVER_TOKEN=... \
  python3 monitor.py
```
