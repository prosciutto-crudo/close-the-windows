#!/usr/bin/env python3
"""Close the windows — Weather Underground PWS temperature monitor.

Polls a Weather Underground personal weather station (PWS) for the current
temperature and sends a Pushover notification *only* when the temperature
crosses above the threshold (default 24 C). It stays quiet until the
temperature drops back below the threshold and rises again, so you get one
ping per heat-up, not a stream.

State (whether we were last above the threshold) is persisted in state.json,
which is committed back to the repo by the GitHub Actions workflow.

Required environment variables:
  WU_STATION_ID    e.g. "IBARCELONA42"
  WU_API_KEY       Weather Underground / weather.com API key
  PUSHOVER_USER    Pushover user key
  PUSHOVER_TOKEN   Pushover application API token

Optional:
  THRESHOLD_C      temperature threshold in Celsius (default 24)
  STATE_FILE       path to the state file (default state.json)
"""

import json
import os
import sys
import urllib.parse
import urllib.request

WU_URL = "https://api.weather.com/v2/pws/observations/current"
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Missing required environment variable: {name}")
    return value


def get_current_temp(station_id: str, api_key: str) -> float:
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
        sys.exit("Observation did not include a temperature reading")
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
        return {"above": False}


def save_state(path: str, state: dict) -> None:
    with open(path, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def main() -> None:
    station_id = env("WU_STATION_ID")
    api_key = env("WU_API_KEY")
    pushover_user = env("PUSHOVER_USER")
    pushover_token = env("PUSHOVER_TOKEN")
    threshold = float(os.environ.get("THRESHOLD_C", "24"))
    state_file = os.environ.get("STATE_FILE", "state.json")

    temp = get_current_temp(station_id, api_key)
    was_above = bool(load_state(state_file).get("above", False))
    now_above = temp > threshold

    print(f"Current temp: {temp:.1f} C | threshold: {threshold:.0f} C | "
          f"was_above={was_above} now_above={now_above}")

    if now_above and not was_above:
        title = "Close the windows \U0001F525"
        message = (f"It's {temp:.1f} C outside (above {threshold:.0f} C). "
                   f"Time to shut the windows and blinds.")
        send_pushover(pushover_user, pushover_token, title, message)
        print("Crossed above threshold -> Pushover notification sent.")
    elif not now_above and was_above:
        print("Dropped back below threshold -> re-armed, no notification.")
    else:
        print("No threshold crossing -> nothing to do.")

    save_state(state_file, {"above": now_above})


if __name__ == "__main__":
    main()
