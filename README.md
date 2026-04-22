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

## Searching near ZIP 94550 (37.6751, -121.7563)...
#
## ==============================================================================
##  Costco Gas Prices — 16 station(s) within 25 miles
## ==============================================================================
##  Location                       Address                    Regular  Premium    Dist
##  ------------------------------ ------------------------- -------- --------  ------
##  Livermore                      2800 INDEPENDENCE DR        $5.399   $5.799    3.6mi
##  Pleasanton                     7200 JOHNSON DRIVE          $5.459   $5.859    8.9mi
##  Danville                       3150 FOSTORIA WAY           $5.399   $5.799   13.9mi
##  Tracy                          3250 W GRANT LINE RD        $5.199   $5.599   16.2mi
##  Newark                         350 NEWPARK MALL            $5.099   $5.659   16.8mi
##  Fremont                        43621 PACIFIC COMMONS BLV   $5.099   $5.659   16.8mi
##  Hayward                        28505 HESPERIAN BLVD        $5.159   $5.559   18.7mi
##  Hayward Business Center        22330 HATHAWAY AVE          $5.299   $5.699   19.0mi
##  Brentwood CA                   5151 HEIDORN RANCH RD       $5.359   $5.759   19.5mi
##  NE San Jose                    1709 AUTOMATION PKWY        $5.159   $5.559   20.9mi
##  Antioch                        2201 VERNE ROBERTS CIR      $5.359   $5.659   23.5mi
##  San Leandro                    1900 DAVIS ST               $5.159   $5.599   23.5mi
##  Santa Clara                    1601 COLEMAN AVE            $5.199   $5.599   24.1mi
##  Sunnyvale                      150 LAWRENCE STATION RD     $5.199   $5.599   24.7mi
##  Concord                        2400 MONUMENT BLVD          $5.399   $5.799   24.7mi
##  San Jose Business Center       2376 S EVERGREEN LOOP       $5.099   $5.599   24.8mi
## ==============================================================================
#
## ──────────────────────────────────────────────────────────────────────────────
##  Station Details:
## ──────────────────────────────────────────────────────────────────────────────
#
##  Livermore (#146) — 3.6 mi away
##    2800 INDEPENDENCE DR, LIVERMORE, CA 94551-7628
##    Phone: (925) 443-6306
##    Regular: $5.399  |  Premium: $5.799
##    Hours: Mon-Fri. 6:00am - 10:00pm / Sat. 6:00am - 8:30pm / Sun. 6:00am - 8:00pm
#
##  Pleasanton (#1341) — 8.9 mi away
##    7200 JOHNSON DRIVE, PLEASANTON, CA 94588-8005
##    Phone: (925) 475-4000
##    Regular: $5.459  |  Premium: $5.859
##    Hours: Mon-Fri. 6:00am - 10:00pm / Sat. 6:00am - 8:30pm / Sun. 6:00am - 8:00pm
#
##  Danville (#21) — 13.9 mi away
##    3150 FOSTORIA WAY, DANVILLE, CA 94526-5553
##    Phone: (925) 277-0407
##    Regular: $5.399  |  Premium: $5.799
##    Hours: Mon-Fri. 6:00am - 10:00pm / Sat. 6:00am - 8:30pm / Sun. 6:00am - 8:00pm
#
##  Tracy (#658) — 16.2 mi away
##    3250 W GRANT LINE RD, TRACY, CA 95304-8427
##    Phone: (209) 830-5340
##    Regular: $5.199  |  Premium: $5.599
##    Hours: Mon-Fri. 6:00am - 10:00pm / Sat. 6:00am - 8:30pm / Sun. 6:00am - 8:00pm
#
##  Newark (#1660) — 16.8 mi away
##    350 NEWPARK MALL, NEWARK, CA 94560-5201
##    Phone: (510) 493-2945
##    Regular: $5.099  |  Premium: $5.659
##    Hours: Mon-Fri. 6:00am - 10:00pm / Sat. 6:00am - 8:00pm / Sun. 6:00am - 8:00pm
#
##  Fremont (#778) — 16.8 mi away
##    43621 PACIFIC COMMONS BLVD, FREMONT, CA 94538-3809
##    Phone: (510) 897-1092
##    Regular: $5.099  |  Premium: $5.659
##    Hours: Mon-Fri. 6:00am - 10:00pm / Sat. 6:00am - 8:30pm / Sun. 6:00am - 8:00pm
#
##  Hayward (#1061) — 18.7 mi away
##    28505 HESPERIAN BLVD, HAYWARD, CA 94545-5008
##    Phone: (510) 921-3128
##    Regular: $5.159  |  Premium: $5.559
##    Hours: Mon-Fri. 5:00am - 10:00pm / Sat. 5:00am - 9:00pm / Sun. 5:00am - 9:00pm
#
##  Hayward Business Center (#823) — 19.0 mi away
##    22330 HATHAWAY AVE, HAYWARD, CA 94541-4861
##    Phone: (510) 259-6600
##    Regular: $5.299  |  Premium: $5.699
##    Hours: Mon-Fri. 5:00am - 10:00pm / Sat. 5:00am - 8:30pm / Sun. 5:00am - 7:30pm
#
##  Brentwood CA (#1662) — 19.5 mi away
##    5151 HEIDORN RANCH RD, BRENTWOOD, CA 94513-0000
##    Phone: (925) 666-0223
##    Regular: $5.359  |  Premium: $5.759
##    Hours: Mon-Fri. 6:00am - 10:00pm / Sat. 6:00am - 8:30pm / Sun. 6:00am - 8:00pm
#
##  NE San Jose (#1004) — 20.9 mi away
##    1709 AUTOMATION PKWY, SAN JOSE, CA 95131-1866
##    Phone: (408) 678-2150
##    Regular: $5.159  |  Premium: $5.559
##    Hours: Mon-Fri. 5:00am - 10:00pm / Sat. 5:00am - 9:00pm / Sun. 5:00am - 9:00pm
#
##  Antioch (#1002) — 23.5 mi away
##    2201 VERNE ROBERTS CIR, ANTIOCH, CA 94509-7911
##    Phone: (925) 757-7130
##    Regular: $5.359  |  Premium: $5.659
##    Hours: Mon-Fri. 6:00am - 10:00pm / Sat. 6:00am - 8:30pm / Sun. 6:00am - 8:00pm
#
##  San Leandro (#118) — 23.5 mi away
##    1900 DAVIS ST, SAN LEANDRO, CA 94577-1209
##    Phone: (510) 562-6708
##    Regular: $5.159  |  Premium: $5.599
##    Hours: Mon-Fri. 6:00am - 10:00pm / Sat. 6:00am - 8:30pm / Sun. 6:00am - 8:00pm
#
##  Santa Clara (#129) — 24.1 mi away
##    1601 COLEMAN AVE, SANTA CLARA, CA 95050-3122
##    Phone: (408) 567-9000
##    Regular: $5.199  |  Premium: $5.599
##    Hours: Mon-Fri. 5:00am - 10:00pm / Sat. 5:00am - 9:00pm / Sun. 5:00am - 9:00pm
#
##  Sunnyvale (#423) — 24.7 mi away
##    150 LAWRENCE STATION RD, SUNNYVALE, CA 94086-5309
##    Phone: (408) 730-1892
##    Regular: $5.199  |  Premium: $5.599
##    Hours: Mon-Fri. 6:00am - 10:00pm / Sat. 6:00am - 8:30pm / Sun. 6:00am - 8:00pm
#
##  Concord (#663) — 24.7 mi away
##    2400 MONUMENT BLVD, CONCORD, CA 94520-3105
##    Phone: (925) 566-4003
##    Regular: $5.399  |  Premium: $5.799
##    Hours: Mon-Fri. 6:00am - 10:00pm / Sat. 6:00am - 8:30pm / Sun. 6:00am - 8:00pm
#
##  San Jose Business Center (#848) — 24.8 mi away
##    2376 S EVERGREEN LOOP, SAN JOSE, CA 95122-4030
##    Phone: (669) 236-4679
##    Regular: $5.099  |  Premium: $5.599
##    Hours: Mon-Fri. 6:00am - 10:00pm / Sat. 6:00am - 8:30pm / Sun. 6:00am - 7:30pm 



# gdrive_backup.py — mirrors your entire Google Drive (and optionally Google Photos) to a local folder and emits a cleanup report.

What it does
- Lists every Drive file (folders resolved to full paths), downloads binaries, and exports Google Docs/Sheets/Slides to Office formats (.docx/.xlsx/.pptx).
- Optionally pulls Google Photos originals into `Photos/YYYY/YYYY-MM-DD/` using the Photos Library API.
- Skips already-downloaded files so it's resumable.
- Writes `_cleanup_report.json` flagging: duplicates (by md5, keep newest), files ≥ `--big-mb` (default 100 MB), items untouched for `--stale-days` (default 730), and everything in Trash.

Setup
1. Google Cloud Console → create OAuth client (Desktop app), enable **Google Drive API** and **Photos Library API**.
2. Save the credentials JSON as `client_secret.json` next to the script.
3. First run opens a browser for consent; token cached in `gdrive_token.json`.

Usage
```
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib tqdm

python gdrive_backup.py --dest ~/GDriveBackup
python gdrive_backup.py --dest ~/GDriveBackup --include-photos
python gdrive_backup.py --dest ~/GDriveBackup --dry-run         # list only
python gdrive_backup.py --dest ~/GDriveBackup --report-only     # skip download, analyze only
python gdrive_backup.py --dest ~/GDriveBackup --include-trashed --big-mb 50 --stale-days 365
```

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