#!/usr/bin/env python3
"""Close/open the windows — indoor vs outdoor temperature monitor.

Optimises for the lowest possible indoor temperature by comparing the outdoor
temperature (a Weather Underground PWS) against the indoor temperature (a Shelly
H&T Gen3, read via the Shelly Cloud API):

  * outdoor drops below indoor (by MARGIN_C)  -> ping "open the windows"
  * outdoor rises above indoor (by MARGIN_C)  -> ping "close the windows"

It alerts *only on the flip*, never on every poll, and a hysteresis margin keeps
it from flapping when the two readings are nearly equal. A quiet-hours guard
suppresses everything between 22:00 and 06:00 Europe/Madrid; because the script
simply doesn't run/act overnight, the first morning run naturally re-checks the
relationship and pings once if it flipped while you slept.

State (whether the windows should currently be open) is persisted in state.json,
committed back to the repo by the GitHub Actions workflow only when it flips.

Required environment variables:
  WU_STATION_ID     Weather Underground PWS id (outdoor source)
  WU_API_KEY        Weather Underground / weather.com API key
  SHELLY_SERVER     Shelly Cloud host, e.g. "https://shelly-267-eu.shelly.cloud"
  SHELLY_DEVICE_ID  Shelly device id, e.g. "d885ac12b894"
  SHELLY_AUTH_KEY   Shelly Cloud authorization key
  PUSHOVER_USER     Pushover user key
  PUSHOVER_TOKEN    Pushover application API token

Optional:
  MARGIN_C          hysteresis deadband in Celsius (default 1.0)
  QUIET_HOURS       "on"/"off" — enable the night-time guard (default on)
  NIGHT_START       quiet-hours start hour, Madrid local (default 22)
  NIGHT_END         quiet-hours end hour, Madrid local (default 6)
  NOTIFY_ON_INIT    "on"/"off" — push the current recommendation on the first
                    run instead of initialising silently (default off)
  MAX_STALE_MIN     ignore the Shelly reading if older than this (default 90)
  STATE_FILE        path to the state file (default state.json)
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

WU_URL = "https://api.weather.com/v2/pws/observations/current"
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"
MADRID = ZoneInfo("Europe/Madrid")


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Missing required environment variable: {name}")
    return value


def get_outdoor_temp(station_id: str, api_key: str) -> float:
    query = urllib.parse.urlencode(
        {
            "stationId": station_id,
            "format": "json",
            "units": "m",  # metric -> temperature in Celsius
            "apiKey": api_key,
        }
    )
    req = urllib.request.Request(f"{WU_URL}?{query}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    observations = data.get("observations") or []
    if not observations:
        sys.exit(f"No observations returned for station {station_id}")

    temp = observations[0].get("metric", {}).get("temp")
    if temp is None:
        sys.exit("Outdoor observation did not include a temperature reading")
    return float(temp)


def get_indoor_temp(server: str, device_id: str, auth_key: str, max_stale_min: float) -> float:
    query = urllib.parse.urlencode({"id": device_id, "auth_key": auth_key})
    url = f"{server.rstrip('/')}/device/status?{query}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    payload = data.get("data") or {}
    status = payload.get("device_status") or {}
    if not payload.get("online", False):
        sys.exit("Shelly reports the device as offline — skipping (no false flip).")

    temp = (status.get("temperature:0") or {}).get("tC")
    if temp is None:
        sys.exit("Shelly status did not include a temperature reading")

    ts = status.get("ts")
    if ts:
        age_min = (time.time() - float(ts)) / 60
        if age_min > max_stale_min:
            sys.exit(f"Shelly reading is {age_min:.0f} min old (> {max_stale_min:.0f}) "
                     f"— skipping to avoid acting on a stale value.")
    return float(temp)


def send_pushover(user: str, token: str, title: str, message: str) -> None:
    payload = urllib.parse.urlencode(
        {"token": token, "user": user, "title": title, "message": message}
    ).encode()
    req = urllib.request.Request(PUSHOVER_URL, data=payload)
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            sys.exit(f"Pushover returned HTTP {resp.status}")


def load_state(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"windows_open": None}


def save_state(path: str, state: dict) -> None:
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def in_quiet_hours(now: datetime, night_start: int, night_end: int) -> bool:
    hour = now.hour
    # Window wraps past midnight (e.g. 22 -> 6): quiet if at/after start OR before end.
    return hour >= night_start or hour < night_end


def main() -> None:
    station_id = env("WU_STATION_ID")
    wu_key = env("WU_API_KEY")
    shelly_server = env("SHELLY_SERVER")
    shelly_device = env("SHELLY_DEVICE_ID")
    shelly_key = env("SHELLY_AUTH_KEY")
    pushover_user = env("PUSHOVER_USER")
    pushover_token = env("PUSHOVER_TOKEN")

    def flag(name: str, default: bool) -> bool:
        raw = os.environ.get(name)
        if raw is None:
            return default
        return raw.strip().lower() in ("on", "true", "1", "yes")

    margin = float(os.environ.get("MARGIN_C", "1.0"))
    quiet_enabled = flag("QUIET_HOURS", True)
    night_start = int(os.environ.get("NIGHT_START", "22"))
    night_end = int(os.environ.get("NIGHT_END", "6"))
    notify_on_init = flag("NOTIFY_ON_INIT", False)
    max_stale_min = float(os.environ.get("MAX_STALE_MIN", "90"))
    state_file = os.environ.get("STATE_FILE", "state.json")

    now = datetime.now(MADRID)
    if quiet_enabled and in_quiet_hours(now, night_start, night_end):
        print(f"Quiet hours ({night_start:02d}:00–{night_end:02d}:00 Madrid, "
              f"now {now:%H:%M}) — skipping. State preserved for the morning check.")
        return

    outdoor = get_outdoor_temp(station_id, wu_key)
    indoor = get_indoor_temp(shelly_server, shelly_device, shelly_key, max_stale_min)
    delta = outdoor - indoor  # positive => warmer outside

    prior = load_state(state_file).get("windows_open")

    # Hysteresis: only flip once outdoor clears indoor by the margin in either
    # direction; inside the deadband we hold the previous recommendation.
    if delta >= margin:
        windows_open = False  # warmer outside -> close
    elif delta <= -margin:
        windows_open = True   # cooler outside -> open
    else:
        windows_open = prior  # within deadband -> hold

    print(f"Outdoor {outdoor:.1f} C | Indoor {indoor:.1f} C | delta {delta:+.1f} C "
          f"| margin {margin:.1f} | prior={prior} -> windows_open={windows_open}")

    if prior is None:
        # First run / freshly seeded: adopt the current recommendation.
        if windows_open is None:
            windows_open = delta < 0  # break the deadband tie on cold start
        if notify_on_init:
            if windows_open:
                send_pushover(
                    pushover_user, pushover_token, "Open the windows",
                    f"Cooler outside: {outdoor:.1f} C vs {indoor:.1f} C indoors. "
                    f"Open up to pull the cool air in.",
                )
            else:
                send_pushover(
                    pushover_user, pushover_token, "Close the windows",
                    f"Warmer outside: {outdoor:.1f} C vs {indoor:.1f} C indoors. "
                    f"Keep the windows and blinds shut.",
                )
            print("No prior state — sent current recommendation (NOTIFY_ON_INIT).")
        else:
            print("No prior state — initialising silently, no notification.")
    elif windows_open and not prior:
        send_pushover(
            pushover_user, pushover_token,
            "Open the windows",
            f"Cooler outside now: {outdoor:.1f} C vs {indoor:.1f} C indoors. "
            f"Open up to pull the cool air in.",
        )
        print("Flipped to OPEN -> Pushover notification sent.")
    elif prior and not windows_open:
        send_pushover(
            pushover_user, pushover_token,
            "Close the windows",
            f"Warmer outside now: {outdoor:.1f} C vs {indoor:.1f} C indoors. "
            f"Shut the windows and blinds to keep the cool in.",
        )
        print("Flipped to CLOSED -> Pushover notification sent.")
    else:
        print("No flip -> nothing to do.")

    save_state(state_file, {"windows_open": windows_open})


if __name__ == "__main__":
    main()
