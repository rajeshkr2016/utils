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
    args = parser.parse_args()

    # Determine coordinates
    if args.zip:
        lat, lng = zip_to_coords(args.zip)
        print(f"Searching near ZIP {args.zip} ({lat:.4f}, {lng:.4f})...")
    elif args.lat is not None and args.lng is not None:
        lat, lng = args.lat, args.lng
        print(f"Searching near ({lat:.4f}, {lng:.4f})...")
    else:
        lat, lng = 37.3382, -121.8863
        print(f"No location specified. Using default: San Jose, CA ({lat:.4f}, {lng:.4f})")
        print("Tip: use --zip <ZIP> or --lat/--lng to specify a location.\n")

    num = min(args.num, 50)
    warehouses = fetch_costco_gas_prices(lat, lng, num)

    if args.json:
        filtered = [w for w in warehouses if (w.get("distance") or 999) <= args.radius]
        print(json.dumps(filtered, indent=2))
    else:
        print_table(warehouses, args.radius)


if __name__ == "__main__":
    main()
