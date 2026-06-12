#!/usr/bin/env python3
"""Close/open the windows — indoor vs outdoor temperature monitor + logger.

Optimises for the lowest possible indoor temperature by comparing the outdoor
temperature (a Weather Underground PWS) against the indoor temperature (a Shelly
H&T Gen3, read via the Shelly Cloud API):

  * outdoor drops below indoor (by MARGIN_C)  -> push "open the windows"
  * outdoor rises above indoor (by MARGIN_C)  -> push "close the windows"

It pushes a Pushover notification *only on the flip*, never on every poll, and a
hysteresis margin keeps it from flapping when the two readings are nearly equal.

Every run also appends a reading (both temps + both humidities) to data.json and
trims it to a rolling WINDOW_HOURS window — that file is the data source for the
dashboard. Data is logged 24/7; the quiet-hours guard only suppresses *pushes*
(22:00–06:00 Madrid), tracked separately via `notified_state` so the first run
after quiet hours still sends one catch-up push if the recommendation flipped
overnight.

data.json shape:
  {
    "updated": <unix int>,            # last poll time
    "windows_open": true|false|null,  # current recommendation (null = uninit)
    "notified_state": true|false|null,# recommendation we last *pushed* about
    "points": [ {"t","out_t","in_t","out_h","in_h"}, ... ]  # rolling window
  }

Required environment variables:
  WU_STATION_ID, WU_API_KEY                       outdoor source
  SHELLY_SERVER, SHELLY_DEVICE_ID, SHELLY_AUTH_KEY indoor source
  PUSHOVER_USER, PUSHOVER_TOKEN                    notifications

Optional:
  MARGIN_C        hysteresis deadband in Celsius (default 1.0)
  QUIET_HOURS     "on"/"off" — suppress pushes at night (default on)
  NIGHT_START     quiet-hours start hour, Madrid local (default 22)
  NIGHT_END       quiet-hours end hour, Madrid local (default 6)
  NOTIFY_ON_INIT  "on"/"off" — push the current recommendation on first run
  WINDOW_HOURS    rolling history window kept in data.json (default 24)
  MAX_STALE_MIN   ignore the Shelly reading if older than this (default 90)
  DATA_FILE       path to the rolling 24h data file (default data.json)
  HISTORY_FILE    path to the never-trimmed CSV archive (default history.csv)
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


def flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("on", "true", "1", "yes")


def get_outdoor(station_id: str, api_key: str):
    """Return (temp_c, humidity_pct) for the WU PWS."""
    query = urllib.parse.urlencode(
        {"stationId": station_id, "format": "json", "units": "m",
         "numericPrecision": "decimal", "apiKey": api_key}
    )
    req = urllib.request.Request(f"{WU_URL}?{query}", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)

    observations = data.get("observations") or []
    if not observations:
        sys.exit(f"No observations returned for station {station_id}")

    obs = observations[0]
    temp = (obs.get("metric") or {}).get("temp")
    if temp is None:
        sys.exit("Outdoor observation did not include a temperature reading")
    humidity = obs.get("humidity")
    return float(temp), (None if humidity is None else float(humidity))


def get_indoor(server: str, device_id: str, auth_key: str, max_stale_min: float):
    """Return (temp_c, humidity_pct) for the Shelly H&T via the Cloud API."""
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

    humidity = (status.get("humidity:0") or {}).get("rh")
    return float(temp), (None if humidity is None else float(humidity))


def send_pushover(user: str, token: str, title: str, message: str) -> None:
    payload = urllib.parse.urlencode(
        {"token": token, "user": user, "title": title, "message": message}
    ).encode()
    req = urllib.request.Request(PUSHOVER_URL, data=payload)
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            sys.exit(f"Pushover returned HTTP {resp.status}")


def load_data(path: str) -> dict:
    try:
        with open(path) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data.setdefault("windows_open", None)
    data.setdefault("notified_state", None)
    data.setdefault("points", [])
    return data


def save_data(path: str, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


HISTORY_HEADER = "t,iso_madrid,out_t,in_t,out_h,in_h,windows_open\n"


def append_history(path: str, point: dict, windows_open) -> None:
    """Append one reading to a never-trimmed CSV (the indefinite archive).

    Separate from data.json (the rolling 24h dashboard feed) — this file grows
    forever for day-over-day analysis. Writes the header once on first creation.
    """
    new_file = not os.path.exists(path)
    iso = datetime.fromtimestamp(point["t"], MADRID).strftime("%Y-%m-%d %H:%M:%S")
    fields = [point["t"], iso, point["out_t"], point["in_t"],
              point["out_h"], point["in_h"], windows_open]
    row = ",".join("" if v is None else str(v) for v in fields) + "\n"
    with open(path, "a") as f:
        if new_file:
            f.write(HISTORY_HEADER)
        f.write(row)


def in_quiet_hours(now: datetime, night_start: int, night_end: int) -> bool:
    hour = now.hour
    # Window wraps past midnight (e.g. 22 -> 6): quiet if at/after start OR before end.
    return hour >= night_start or hour < night_end


def open_msg(outdoor, indoor):
    return ("Open the windows",
            f"Cooler outside: {outdoor:.1f} C vs {indoor:.1f} C indoors. "
            f"Open up to pull the cool air in.")


def close_msg(outdoor, indoor):
    return ("Close the windows",
            f"Warmer outside: {outdoor:.1f} C vs {indoor:.1f} C indoors. "
            f"Shut the windows and blinds to keep the cool in.")


def main() -> None:
    station_id = env("WU_STATION_ID")
    wu_key = env("WU_API_KEY")
    shelly_server = env("SHELLY_SERVER")
    shelly_device = env("SHELLY_DEVICE_ID")
    shelly_key = env("SHELLY_AUTH_KEY")
    pushover_user = env("PUSHOVER_USER")
    pushover_token = env("PUSHOVER_TOKEN")

    margin = float(os.environ.get("MARGIN_C", "1.0"))
    quiet_enabled = flag("QUIET_HOURS", True)
    night_start = int(os.environ.get("NIGHT_START", "22"))
    night_end = int(os.environ.get("NIGHT_END", "6"))
    notify_on_init = flag("NOTIFY_ON_INIT", False)
    window_hours = float(os.environ.get("WINDOW_HOURS", "24"))
    max_stale_min = float(os.environ.get("MAX_STALE_MIN", "90"))
    data_file = os.environ.get("DATA_FILE", "data.json")
    history_file = os.environ.get("HISTORY_FILE", "history.csv")

    outdoor_t, outdoor_h = get_outdoor(station_id, wu_key)
    indoor_t, indoor_h = get_indoor(shelly_server, shelly_device, shelly_key, max_stale_min)
    delta = outdoor_t - indoor_t  # positive => warmer outside

    data = load_data(data_file)
    prior_open = data["windows_open"]
    notified = data["notified_state"]

    # Hysteresis: only flip once outdoor clears indoor by the margin in either
    # direction; inside the deadband we hold the previous recommendation.
    if delta >= margin:
        windows_open = False  # warmer outside -> close
    elif delta <= -margin:
        windows_open = True   # cooler outside -> open
    else:
        windows_open = prior_open
    if windows_open is None:
        windows_open = delta < 0  # cold start tie-break

    now = datetime.now(MADRID)
    quiet = quiet_enabled and in_quiet_hours(now, night_start, night_end)

    print(f"Outdoor {outdoor_t:.1f} C / {outdoor_h}%RH | Indoor {indoor_t:.1f} C / {indoor_h}%RH "
          f"| delta {delta:+.1f} (margin {margin:.1f}) | prior={prior_open} notified={notified} "
          f"-> windows_open={windows_open} | quiet={quiet}")

    # --- notification decision (separate from data logging) ---
    if quiet:
        print("Quiet hours — logging only, no push. Catch-up deferred to morning.")
    elif notified is None:
        if notify_on_init:
            send_pushover(pushover_user, pushover_token,
                          *(open_msg if windows_open else close_msg)(outdoor_t, indoor_t))
            notified = windows_open
            print("First run — pushed current recommendation (NOTIFY_ON_INIT).")
        else:
            print("First run — initialising silently, no push.")
    elif windows_open != notified:
        send_pushover(pushover_user, pushover_token,
                      *(open_msg if windows_open else close_msg)(outdoor_t, indoor_t))
        notified = windows_open
        print(f"Flipped to {'OPEN' if windows_open else 'CLOSED'} -> push sent.")
    else:
        print("No flip -> no push.")

    # --- always log the data point ---
    now_ts = int(time.time())
    point = {"t": now_ts, "out_t": round(outdoor_t, 1), "in_t": round(indoor_t, 1),
             "out_h": None if outdoor_h is None else round(outdoor_h, 1),
             "in_h": None if indoor_h is None else round(indoor_h, 1)}
    cutoff = now_ts - int(window_hours * 3600)
    points = [p for p in data["points"] if p.get("t", 0) >= cutoff]
    points.append(point)

    save_data(data_file, {
        "updated": now_ts,
        "windows_open": windows_open,
        "notified_state": notified,
        "points": points,
    })
    append_history(history_file, point, windows_open)
    print(f"Logged point; {len(points)} points in the last {window_hours:.0f}h "
          f"(+1 appended to {history_file}).")


if __name__ == "__main__":
    main()
