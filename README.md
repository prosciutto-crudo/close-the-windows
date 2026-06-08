# close-the-windows

Watches a [Weather Underground](https://www.wunderground.com/) personal weather
station (PWS) and sends a [Pushover](https://pushover.net/) notification when the
outdoor temperature crosses **above 24 °C** — your cue to shut the windows and
blinds before the house heats up.

Runs entirely in the cloud via GitHub Actions. Nothing runs locally.

## How it works

- `monitor.py` (stdlib only — no dependencies) calls the WU PWS current-observation
  API, reads the temperature in Celsius, and compares it to the threshold.
- It notifies **only on an upward crossing**: one ping when the temperature rises
  above 24 °C, then silence until it drops back below and rises again.
- `state.json` (`{"above": true/false}`) remembers whether we were last above the
  threshold. The workflow commits it back only when it flips, so there's no commit spam.
- `.github/workflows/monitor.yml` runs every 15 minutes during daytime
  (≈07:00–23:00 Europe/Madrid) and can also be triggered manually via
  **Actions → Temperature monitor → Run workflow**.

## Configuration

Set these as repository **Actions secrets** (Settings → Secrets and variables → Actions):

| Secret | What it is |
|---|---|
| `WU_STATION_ID` | Your Weather Underground station ID, e.g. `IBARCELONA42` |
| `WU_API_KEY` | Weather Underground / weather.com API key |
| `PUSHOVER_USER` | Your Pushover user key |
| `PUSHOVER_TOKEN` | Your Pushover application API token |

The threshold is set in the workflow (`THRESHOLD_C: "24"`); change it there.

## Run locally (optional)

```bash
WU_STATION_ID=... WU_API_KEY=... PUSHOVER_USER=... PUSHOVER_TOKEN=... \
  python3 monitor.py
```
