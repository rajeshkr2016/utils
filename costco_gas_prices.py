#!/usr/bin/env python3
"""
Costco Gas Price Fetcher

Fetches regular and premium gas prices from Costco warehouse locations
near a given ZIP code or latitude/longitude coordinates.

Requires: curl_cffi (pip install curl_cffi)

Usage:
    python costco_gas_prices.py                          # Default: San Jose, CA
    python costco_gas_prices.py --zip 90210              # By ZIP code
    python costco_gas_prices.py --lat 37.3 --lng -121.9  # By coordinates
    python costco_gas_prices.py --zip 90210 --radius 30  # Custom radius in miles
    python costco_gas_prices.py --zip 90210 --json       # Output as JSON
"""

import argparse
import json
import math
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlencode

from curl_cffi import requests as cffi_requests


COSTCO_API_URL = "https://www.costco.com/AjaxWarehouseBrowseLookupView"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def zip_to_coords(zip_code: str) -> tuple[float, float]:
    """Convert a US ZIP code to latitude/longitude using Nominatim."""
    params = urlencode({
        "postalcode": zip_code,
        "country": "US",
        "format": "json",
        "limit": "1",
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = Request(url, headers={"User-Agent": "CostcoGasPriceFetcher/1.0"})
    try:
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"Error geocoding ZIP code: {e}", file=sys.stderr)
        sys.exit(1)

    if not data:
        print(f"Could not find coordinates for ZIP code: {zip_code}", file=sys.stderr)
        sys.exit(1)

    return float(data[0]["lat"]), float(data[0]["lon"])


def fetch_costco_gas_prices(lat: float, lng: float, num_warehouses: int = 25) -> list[dict]:
    """Fetch gas prices from Costco warehouses near the given coordinates."""
    resp = cffi_requests.get(
        COSTCO_API_URL,
        params={
            "numOfWarehouses": str(num_warehouses),
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
        timeout=15,
    )

    if resp.status_code != 200:
        print(f"Costco API returned HTTP {resp.status_code}", file=sys.stderr)
        sys.exit(1)

    raw = resp.json()

    # Response is a JSON array; first element is a boolean — skip it
    if not isinstance(raw, list) or len(raw) < 2:
        print("Unexpected API response format.", file=sys.stderr)
        return []

    warehouses = []
    for item in raw[1:]:
        if not isinstance(item, dict):
            continue

        gas_prices = item.get("gasPrices")
        if not gas_prices:
            continue

        warehouse = {
            "id": item.get("stlocID"),
            "name": item.get("locationName", "Unknown"),
            "address": _build_address(item),
            "phone": (item.get("phone") or "").strip(),
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "distance": item.get("distance"),
            "regular": gas_prices.get("regular"),
            "premium": gas_prices.get("premium"),
            "gas_hours": _format_hours(item.get("gasStationHours", [])),
        }
        warehouses.append(warehouse)

    warehouses.sort(key=lambda w: w.get("distance") or 999)
    return warehouses


def _build_address(item: dict) -> str:
    """Build a readable address string from warehouse data fields."""
    parts = []
    for field in ("address1", "address2"):
        val = item.get(field, "")
        if val and val.strip():
            parts.append(val.strip())
    city = item.get("city", "")
    state = item.get("state", "")
    zip_code = item.get("zipCode", "") or item.get("postalCode", "")
    if city or state or zip_code:
        parts.append(f"{city}, {state} {zip_code}".strip())
    return ", ".join(parts) if parts else "N/A"


def _format_hours(hours_list: list) -> list[str]:
    """Format gas station hours into readable strings."""
    result = []
    for h in hours_list:
        title = (h.get("title") or "").strip()
        time = (h.get("time") or "").strip()
        if title and time:
            result.append(f"{title} {time}")
    return result


def _format_price(price) -> str:
    """Format a price value for display."""
    if price is None:
        return "  N/A  "
    try:
        return f"${float(price):.3f}"
    except (TypeError, ValueError):
        return "  N/A  "


def print_table(warehouses: list[dict], radius: float):
    """Print gas prices in a formatted table."""
    results = [w for w in warehouses if (w.get("distance") or 999) <= radius]

    if not results:
        print("\nNo Costco gas stations found within the specified radius.")
        return

    print(f"\n{'='*78}")
    print(f" Costco Gas Prices — {len(results)} station(s) within {radius:.0f} miles")
    print(f"{'='*78}")
    print(f" {'Location':<30} {'Address':<25} {'Regular':>8} {'Premium':>8}  {'Dist':>6}")
    print(f" {'-'*30} {'-'*25} {'-'*8} {'-'*8}  {'-'*6}")

    for w in results:
        name = w["name"][:30]
        addr_short = w["address"].split(",")[0][:25]
        regular = _format_price(w["regular"])
        premium = _format_price(w["premium"])
        dist = w.get("distance") or 0
        print(f" {name:<30} {addr_short:<25} {regular:>8} {premium:>8}  {dist:>5.1f}mi")

    print(f"{'='*78}")

    # Show detailed info below
    print(f"\n{'─'*78}")
    print(" Station Details:")
    print(f"{'─'*78}")
    for w in results:
        dist = w.get("distance") or 0
        print(f"\n {w['name']} (#{w['id']}) — {dist:.1f} mi away")
        print(f"   {w['address']}")
        if w["phone"]:
            print(f"   Phone: {w['phone']}")
        print(f"   Regular: {_format_price(w['regular'])}  |  Premium: {_format_price(w['premium'])}")
        if w["gas_hours"]:
            print(f"   Hours: {' / '.join(w['gas_hours'])}")
    print()


HISTORY_FILE = "costco_gas_history.json"


def _load_history(path: str = HISTORY_FILE) -> list[dict]:
    """Load historical fetches from disk. Returns a list of {timestamp, prices} entries."""
    import os
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _append_history(warehouses: list[dict], radius: float, path: str = HISTORY_FILE) -> list[dict]:
    """Append current fetch to history file and return the full history."""
    from datetime import datetime

    history = _load_history(path)

    # Filter to California stations within radius
    entry_prices = {}
    for w in warehouses:
        if (w.get("distance") or 999) > radius:
            continue
        try:
            reg = float(w["regular"]) if w.get("regular") else None
            pre = float(w["premium"]) if w.get("premium") else None
        except (TypeError, ValueError):
            reg, pre = None, None
        if reg is None and pre is None:
            continue
        entry_prices[w["name"]] = {"regular": reg, "premium": pre,
                                    "distance": w.get("distance") or 0}

    entry = {
        "timestamp": datetime.now().isoformat(timespec="minutes"),
        "prices": entry_prices,
    }
    history.append(entry)

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except OSError as e:
        print(f"Warning: could not write history file: {e}", file=sys.stderr)

    return history


def write_mermaid_markdown(warehouses: list[dict], radius: float, output_path: str,
                           origin_label: str = "", history_path: str = HISTORY_FILE):
    """Write a Markdown report with two historical time-series Mermaid charts:
      1. California average (regular & premium) over time
      2. Per-location regular prices over time — one line per location."""
    from datetime import datetime

    # Append current fetch to persistent history
    history = _append_history(warehouses, radius, history_path)

    if not history:
        print("No data to report — skipping Markdown report.")
        return

    # x-axis: timestamps of each fetch
    timestamps = [h["timestamp"] for h in history]
    # Short timestamp labels (e.g. "04-14 16:04")
    ts_labels = []
    for ts in timestamps:
        try:
            dt = datetime.fromisoformat(ts)
            ts_labels.append(dt.strftime("%m-%d %H:%M"))
        except ValueError:
            ts_labels.append(ts)
    ts_labels_quoted = [f'"{t}"' for t in ts_labels]

    # Chart 1 data: California-wide averages over time
    reg_avgs, pre_avgs = [], []
    for h in history:
        regs = [p["regular"] for p in h["prices"].values() if p.get("regular") is not None]
        pres = [p["premium"] for p in h["prices"].values() if p.get("premium") is not None]
        reg_avgs.append(sum(regs) / len(regs) if regs else 0)
        pre_avgs.append(sum(pres) / len(pres) if pres else 0)

    all_avg_prices = [p for p in reg_avgs + pre_avgs if p > 0]
    avg_y_min = max(0, min(all_avg_prices) - 0.15) if all_avg_prices else 0
    avg_y_max = max(all_avg_prices) + 0.15 if all_avg_prices else 6

    reg_avg_str = [f"{v:.3f}" for v in reg_avgs]
    pre_avg_str = [f"{v:.3f}" for v in pre_avgs]

    # Chart 2 data: per-location regular prices over time (one line per location)
    # Collect all location names that have ever appeared in history
    all_locations = []
    seen = set()
    for h in history:
        for name in h["prices"]:
            if name not in seen:
                seen.add(name)
                all_locations.append(name)

    # For each location, build a series of regular prices over time (0 when missing)
    loc_series = {}
    loc_all_prices = []
    for name in all_locations:
        series = []
        for h in history:
            price = h["prices"].get(name, {}).get("regular")
            series.append(price if price is not None else 0)
            if price is not None:
                loc_all_prices.append(price)
        loc_series[name] = series

    loc_y_min = max(0, min(loc_all_prices) - 0.15) if loc_all_prices else 0
    loc_y_max = max(loc_all_prices) + 0.15 if loc_all_prices else 6

    # Build the report
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    header = f"# Costco Gas Prices — California Historical Report\n\n"
    header += f"Generated: {now}  \n"
    if origin_label:
        header += f"Search origin: {origin_label}  \n"
    header += f"Radius: {radius:.0f} miles  \n"
    header += f"Locations tracked: {len(all_locations)}  \n"
    header += f"Historical snapshots: {len(history)}  \n"
    header += f"History file: `{history_path}`\n\n"

    # Chart 1: CA-wide averages
    chart1 = (
        "## 1. California Average Over Time\n\n"
        "Average Regular and Premium prices across all nearby Costco warehouses "
        "at each snapshot.\n\n"
        "```mermaid\n"
        "---\n"
        "config:\n"
        "    xyChart:\n"
        "        width: 900\n"
        "        height: 420\n"
        "---\n"
        "xychart-beta\n"
        '    title "CA Avg Costco Gas Price — Regular (lower) vs Premium (upper)"\n'
        f"    x-axis [{', '.join(ts_labels_quoted)}]\n"
        f'    y-axis "Avg Price ($/gal)" {avg_y_min:.2f} --> {avg_y_max:.2f}\n'
        f"    line [{', '.join(reg_avg_str)}]\n"
        f"    line [{', '.join(pre_avg_str)}]\n"
        "```\n\n"
    )

    # Chart 2: per-location lines over time (Regular price)
    loc_lines = "\n".join(
        f"    line [{', '.join(f'{v:.3f}' for v in loc_series[name])}]"
        for name in all_locations
    )
    legend = "\n".join(
        f"{i+1}. **{name}**" for i, name in enumerate(all_locations)
    )
    chart2 = (
        "## 2. Per-Location Historical Pricing (Regular)\n\n"
        "Each line represents one Costco warehouse, plotting its Regular "
        "price at every snapshot.\n\n"
        "```mermaid\n"
        "---\n"
        "config:\n"
        "    xyChart:\n"
        "        width: 1000\n"
        "        height: 500\n"
        "---\n"
        "xychart-beta\n"
        '    title "Regular Price Over Time — All Locations"\n'
        f"    x-axis [{', '.join(ts_labels_quoted)}]\n"
        f'    y-axis "Regular ($/gal)" {loc_y_min:.2f} --> {loc_y_max:.2f}\n'
        f"{loc_lines}\n"
        "```\n\n"
        "**Line legend (in plotting order):**\n\n"
        f"{legend}\n\n"
    )

    # Latest snapshot summary table
    latest = history[-1]["prices"]
    latest_rows = sorted(latest.items(), key=lambda kv: kv[1].get("distance") or 999)
    table = "## Latest Snapshot\n\n"
    table += f"Snapshot time: `{history[-1]['timestamp']}`\n\n"
    table += "| # | Location | Distance (mi) | Regular ($) | Premium ($) |\n"
    table += "|---|----------|---------------|-------------|-------------|\n"
    for idx, (name, p) in enumerate(latest_rows, 1):
        reg = f"{p['regular']:.3f}" if p.get("regular") is not None else "N/A"
        pre = f"{p['premium']:.3f}" if p.get("premium") is not None else "N/A"
        dist = p.get("distance") or 0
        table += f"| {idx} | {name} | {dist:.1f} | {reg} | {pre} |\n"

    content = header + chart1 + chart2 + table
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Wrote historical Mermaid report to {output_path} "
          f"({len(history)} snapshot(s), {len(all_locations)} location(s))")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch regular and premium gas prices from nearby Costco locations."
    )
    parser.add_argument("--zip", type=str, help="US ZIP code to search near")
    parser.add_argument("--lat", type=float, help="Latitude (use with --lng)")
    parser.add_argument("--lng", type=float, help="Longitude (use with --lat)")
    parser.add_argument("--radius", type=float, default=25,
                        help="Search radius in miles (default: 25)")
    parser.add_argument("--num", type=int, default=25,
                        help="Max warehouses to fetch (default: 25, max: 50)")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON")
    parser.add_argument("--md", type=str, nargs="?", const="costco_gas_report.md",
                        help="Write a Markdown report with Mermaid line charts "
                             "(default path: costco_gas_report.md)")
    args = parser.parse_args()

    # Determine coordinates
    origin_label = ""
    zip_code = args.zip or "94550"
    if args.lat is not None and args.lng is not None:
        lat, lng = args.lat, args.lng
        origin_label = f"({lat:.4f}, {lng:.4f})"
        print(f"Searching near {origin_label}...")
    else:
        lat, lng = zip_to_coords(zip_code)
        origin_label = f"ZIP {zip_code} ({lat:.4f}, {lng:.4f})"
        if args.zip:
            print(f"Searching near {origin_label}...")
        else:
            print(f"No location specified. Using default ZIP: {origin_label}\n")

    num = min(args.num, 50)
    warehouses = fetch_costco_gas_prices(lat, lng, num)

    if args.json:
        filtered = [w for w in warehouses if (w.get("distance") or 999) <= args.radius]
        print(json.dumps(filtered, indent=2))
    else:
        print_table(warehouses, args.radius)

    if args.md:
        write_mermaid_markdown(warehouses, args.radius, args.md, origin_label)


if __name__ == "__main__":
    main()
