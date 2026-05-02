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
import traceback
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from curl_cffi import requests as cffi_requests

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
ZIP_CACHE_PATH = ROOT / "zip_cache.json"
DATA_DIR = ROOT / "pwa" / "data"
HISTORY_LIMIT = 1000

COSTCO_API_URL = "https://www.costco.com/AjaxWarehouseBrowseLookupView"
ZIPPOPOTAM_URL = "https://api.zippopotam.us/us/{zip}"
USER_AGENT = "CostcoGasPriceFetcher/1.0 (github actions cron)"


def load_zip_cache() -> dict:
    if ZIP_CACHE_PATH.exists():
        try:
            return json.loads(ZIP_CACHE_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_zip_cache(cache: dict) -> None:
    ZIP_CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")


def geocode_zip(zip_code: str, cache: dict) -> tuple[float, float, str]:
    if zip_code in cache:
        c = cache[zip_code]
        return float(c["lat"]), float(c["lng"]), c["label"]

    # Public geocoders rate-limit GitHub Actions IPs aggressively. Try once
    # and on any failure, surface a clear message asking the user to populate
    # costco_gas/zip_cache.json manually (one entry per ZIP).
    try:
        url = ZIPPOPOTAM_URL.format(zip=zip_code)
        req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        places = data.get("places") or []
        if not places:
            raise RuntimeError("zippopotam returned no places")
        p = places[0]
        lat = float(p["latitude"])
        lng = float(p["longitude"])
        city = (p.get("place name") or "").strip()
        state = (p.get("state abbreviation") or p.get("state") or "").strip()
        label = ", ".join(s for s in (city, state) if s) or zip_code
    except Exception as e:
        raise RuntimeError(
            f"Geocode failed for ZIP {zip_code} ({e}). "
            f"Add an entry to costco_gas/zip_cache.json: "
            f'{{"{zip_code}": {{"lat": <num>, "lng": <num>, "label": "City, ST"}}}}'
        ) from e

    cache[zip_code] = {"lat": lat, "lng": lng, "label": label}
    return lat, lng, label


def fetch_costco(lat: float, lng: float, num: int = 50) -> list[dict]:
    # Costco's API silently misbehaves above ~50 (returns far fewer rows).
    num = min(num, 50)
    common_headers = {
        "Accept-Language": "en-US,en;q=0.9",
    }
    api_headers = {
        **common_headers,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.costco.com/warehouse-locations",
    }
    api_params = {
        "numOfWarehouses": str(num),
        "hasGas": "true",
        "populateWarehouseDetails": "true",
        "latitude": str(lat),
        "longitude": str(lng),
        "countryCode": "US",
    }

    last_err = None
    for attempt in range(2):
        try:
            resp = cffi_requests.get(
                COSTCO_API_URL,
                params=api_params,
                headers=api_headers,
                impersonate="chrome",
                timeout=20,
            )
            resp.raise_for_status()
            break
        except Exception as e:
            last_err = e
            status = getattr(getattr(e, "response", None), "status_code", None)
            if attempt == 0 and status == 429:
                print("Costco returned 429; sleeping 30s before single retry",
                      file=sys.stderr)
                time.sleep(30)
                continue
            raise
    else:
        raise last_err

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

    cache = load_zip_cache()
    cache_dirty = False
    print(f"Loaded zip_cache.json: {sorted(cache.keys()) or '(empty)'}", file=sys.stderr)

    # Load any existing index so we can preserve entries on partial failure.
    index_path = DATA_DIR / "index.json"
    existing_by_zip: dict[str, dict] = {}
    if index_path.exists():
        try:
            for entry in json.loads(index_path.read_text()).get("zips", []):
                if isinstance(entry, dict) and entry.get("zip"):
                    existing_by_zip[entry["zip"]] = entry
        except (json.JSONDecodeError, OSError):
            pass

    now = datetime.now(timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z")
    succeeded: dict[str, dict] = {}
    errors: dict[str, str] = {}

    for zip_code in zips:
        try:
            had_cache = zip_code in cache
            lat, lng, label = geocode_zip(zip_code, cache)
            if not had_cache:
                cache_dirty = True
            warehouses = fetch_costco(lat, lng)
            filtered = [w for w in warehouses if (w.get("distance") or 999) <= radius]
        except Exception as e:
            print(f"[{zip_code}] failed ({type(e).__name__}): {e}", file=sys.stderr)
            traceback.print_exc()
            errors[zip_code] = str(e)
            continue

        write_snapshot(zip_code, lat, lng, label, filtered, radius, now)
        append_history(zip_code, filtered, now)
        succeeded[zip_code] = {"zip": zip_code, "lat": lat, "lng": lng, "label": label}
        print(f"[{zip_code}] {label}: {len(filtered)} stations within {radius}mi")

    if cache_dirty:
        save_zip_cache(cache)

    # Merge: prefer fresh successes, fall back to existing entries for zips
    # that failed this run but were known before. Only rewrite index.json if
    # we have at least one fresh success — otherwise the prior good data stays.
    if succeeded:
        merged_zips = []
        for zip_code in zips:
            if zip_code in succeeded:
                merged_zips.append(succeeded[zip_code])
            elif zip_code in existing_by_zip:
                merged_zips.append(existing_by_zip[zip_code])
        index_path.write_text(json.dumps({
            "updated": now,
            "radius": radius,
            "zips": merged_zips,
            "errors": errors,
        }, indent=2))
    else:
        print("No zips succeeded — leaving existing index.json untouched.", file=sys.stderr)

    if zips and not succeeded:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
