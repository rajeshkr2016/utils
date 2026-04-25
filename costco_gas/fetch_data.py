#!/usr/bin/env python3
"""GitHub Actions cron entry point.

Reads costco_gas/config.json for the list of ZIPs to track, fetches gas
prices for each via Costco's warehouse locator, and writes static JSON files
into costco_gas/pwa/data/ for the PWA to read.

Output files:
  pwa/data/index.json            — list of zips + last-updated timestamp
  pwa/data/<zip>.json            — latest snapshot for one zip
  pwa/data/<zip>_history.json    — appended price history (capped)
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from curl_cffi import requests as cffi_requests

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
DATA_DIR = ROOT / "pwa" / "data"
HISTORY_LIMIT = 1000

COSTCO_API_URL = "https://www.costco.com/AjaxWarehouseBrowseLookupView"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "CostcoGasPriceFetcher/1.0 (github actions cron)"


def geocode_zip(zip_code: str) -> tuple[float, float, str]:
    params = urlencode({
        "postalcode": zip_code,
        "country": "US",
        "format": "json",
        "addressdetails": "1",
        "limit": "1",
    })
    req = Request(f"{NOMINATIM_URL}?{params}",
                  headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    if not data:
        raise RuntimeError(f"No coordinates for ZIP {zip_code}")
    entry = data[0]
    addr = entry.get("address") or {}
    city = (addr.get("city") or addr.get("town") or addr.get("village")
            or addr.get("hamlet") or "")
    state = addr.get("state") or ""
    label = ", ".join(p for p in (city, state) if p) or zip_code
    return float(entry["lat"]), float(entry["lon"]), label


def fetch_costco(lat: float, lng: float, num: int = 25) -> list[dict]:
    resp = cffi_requests.get(
        COSTCO_API_URL,
        params={
            "numOfWarehouses": str(num),
            "hasGas": "true",
            "populateWarehouseDetails": "true",
            "latitude": str(lat),
            "longitude": str(lng),
            "countryCode": "US",
        },
        headers={
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.costco.com/warehouse-locations",
        },
        impersonate="chrome",
        timeout=20,
    )
    resp.raise_for_status()
    raw = resp.json()
    if not isinstance(raw, list) or len(raw) < 2:
        raise RuntimeError("Unexpected upstream shape")

    out = []
    for item in raw[1:]:
        if not isinstance(item, dict):
            continue
        gp = item.get("gasPrices")
        if not gp:
            continue
        out.append({
            "id": item.get("stlocID"),
            "name": item.get("locationName") or "Unknown",
            "address": _build_address(item),
            "phone": (item.get("phone") or "").strip(),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "distance": item.get("distance"),
            "regular": _num(gp.get("regular")),
            "premium": _num(gp.get("premium")),
        })
    out.sort(key=lambda w: w.get("distance") or 999)
    return out


def _build_address(item: dict) -> str:
    parts = []
    for f in ("address1", "address2"):
        v = (item.get(f) or "").strip()
        if v:
            parts.append(v)
    city = item.get("city") or ""
    state = item.get("state") or ""
    zc = item.get("zipCode") or item.get("postalCode") or ""
    if city or state or zc:
        parts.append(f"{city}, {state} {zc}".strip())
    return ", ".join(parts) or "N/A"


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def write_snapshot(zip_code: str, lat: float, lng: float, label: str,
                   filtered: list[dict], radius: float, now: str) -> None:
    snap = {
        "zip": zip_code,
        "label": label,
        "origin": {"lat": lat, "lng": lng},
        "radius": radius,
        "updated": now,
        "warehouses": filtered,
    }
    (DATA_DIR / f"{zip_code}.json").write_text(json.dumps(snap, indent=2))


def append_history(zip_code: str, filtered: list[dict], now: str) -> None:
    prices = {}
    for w in filtered:
        if w["regular"] is None and w["premium"] is None:
            continue
        prices[w["name"]] = {
            "regular": w["regular"],
            "premium": w["premium"],
            "distance": w.get("distance") or 0,
        }
    if not prices:
        return
    path = DATA_DIR / f"{zip_code}_history.json"
    history = []
    if path.exists():
        try:
            history = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            history = []
    if history and history[-1].get("prices") == prices:
        return  # no change since last snapshot
    history.append({"timestamp": now, "prices": prices})
    history = history[-HISTORY_LIMIT:]
    path.write_text(json.dumps(history, indent=2))


def main() -> int:
    cfg = json.loads(CONFIG_PATH.read_text())
    zips = cfg.get("zips") or []
    radius = float(cfg.get("radius", 25))
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z")
    index = {"updated": now, "radius": radius, "zips": [], "errors": {}}

    for i, zip_code in enumerate(zips):
        if i:
            time.sleep(1.1)  # be polite to Nominatim
        try:
            lat, lng, label = geocode_zip(zip_code)
            warehouses = fetch_costco(lat, lng)
            filtered = [w for w in warehouses if (w.get("distance") or 999) <= radius]
        except Exception as e:
            print(f"[{zip_code}] failed: {e}", file=sys.stderr)
            index["errors"][zip_code] = str(e)
            continue

        write_snapshot(zip_code, lat, lng, label, filtered, radius, now)
        append_history(zip_code, filtered, now)
        index["zips"].append({"zip": zip_code, "lat": lat, "lng": lng, "label": label})
        print(f"[{zip_code}] {label}: {len(filtered)} stations within {radius}mi")

    (DATA_DIR / "index.json").write_text(json.dumps(index, indent=2))

    if zips and not index["zips"]:
        print("All zips failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
