# close-the-windows

Compares the **outdoor** temperature (a [Weather Underground](https://www.wunderground.com/)
personal weather station) against the **indoor** temperature (a [Shelly H&T Gen3](https://kb.shelly.cloud/knowledge-base/shelly-h-t-gen3)
read over the Shelly Cloud API) and sends a [Pushover](https://pushover.net/) push
when the relationship flips — so you can keep the house as cool as possible:

- outdoor drops **below** indoor → **"open the windows"** (pull the cool air in)
- outdoor rises **above** indoor → **"close the windows"** (keep the cool in)

Runs entirely in the cloud via GitHub Actions. Nothing runs locally.

## How it works

- `monitor.py` (stdlib only — no dependencies) reads the outdoor temp from the WU
  PWS API and the indoor temp from the Shelly Cloud API
  (`/device/status?id=…&auth_key=…`, temperature at `data.device_status["temperature:0"].tC`).
- It notifies **only on a flip** (open↔close), never on every poll. A **hysteresis
  margin** (`MARGIN_C`, default 1 °C) is the deadband: the recommendation only changes
  once outdoor clears indoor by that margin, so it won't flap when the two are close.
- **Quiet hours 22:00–06:00 Europe/Madrid** — the script exits early and doesn't touch
  state. Because it neither runs nor updates state overnight, the first morning run
  simply re-checks the relationship and pings once if it flipped while you slept.
- A **staleness guard** (`MAX_STALE_MIN`, default 90) and an offline check stop a dead
  or sleeping sensor from triggering a false flip.
- `state.json` (`{"windows_open": true/false/null}`) remembers the current recommendation;
  `null` means "uninitialised" so the first run adopts the current state silently. The
  workflow commits it back only when it flips — no commit spam.
- `.github/workflows/monitor.yml` runs every 20 min over the Madrid daytime window
  (cron `*/20 4-20 * * *` UTC; the in-script guard trims it precisely to 06:00–22:00
  across DST). ~48 runs/day ≈ 1,440 Actions-min/month, comfortably under the 2,000
  free private-repo minutes — so there's **no self-disable/re-arm dance** anymore.
- The workflow has a manual **Run workflow** button (Actions tab) as a safety valve.

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

`MARGIN_C` (deadband) is set in the workflow; `NIGHT_START`/`NIGHT_END`/`MAX_STALE_MIN`
are optional overrides read by `monitor.py`.

## Run locally (optional)

```bash
WU_STATION_ID=... WU_API_KEY=... \
SHELLY_SERVER=... SHELLY_DEVICE_ID=... SHELLY_AUTH_KEY=... \
PUSHOVER_USER=... PUSHOVER_TOKEN=... \
  python3 monitor.py
```
