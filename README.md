Utilties that help to get details for day to day requirements use

# costco_gas_prices.py — a Python app that fetches real-time regular and premium gas prices from Costco warehouse locations.

How it works
Queries Costco's internal warehouse lookup API (AjaxWarehouseBrowseLookupView) using curl_cffi to bypass Akamai bot protection via browser TLS fingerprint impersonation
Geocodes ZIP codes to coordinates using OpenStreetMap Nominatim (free, no API key)
Displays prices sorted by distance with station details and hours
Usage

## Activate the venv first
source .venv/bin/activate

## Search by ZIP code
python costco_gas_prices.py --zip 90210

## Search by coordinates
python costco_gas_prices.py --lat 37.3 --lng -121.9

## Custom radius (default 25 miles)
python costco_gas_prices.py --zip 95134 --radius 15

## JSON output (for piping to other tools)
python costco_gas_prices.py --zip 95134 --json

## Default: San Jose, CA
python costco_gas_prices.py
Dependency
One external package required: curl_cffi (already installed in .venv).

# py2notebook.py converts any .py file to a valid Jupyter .ipynb notebook.

How it splits cells
Python source	Notebook cell type
Module docstring ("""...""")	Markdown
Comment blocks (2+ # ... lines)	Markdown
## %% or # --- markers	New cell boundary
## %% Section Title	Markdown heading
def / class at top level	Auto-splits into a new code cell
Everything else	Code
Usage

python py2notebook.py script.py                  # Creates script.ipynb
python py2notebook.py script.py -o output.ipynb  # Custom output path
python py2notebook.py script.py --no-split       # Don't auto-split on def/class
No external dependencies — uses only the Python standard library.