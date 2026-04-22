"""gdrive_backup.py — Download all Google Drive files (and optionally Google Photos)
to a local mirror and suggest cleanup (duplicates, huge files, stale/trashed items).

Auth
----
1. Create an OAuth client (Desktop app) at https://console.cloud.google.com/apis/credentials
2. Enable "Google Drive API" and (optional) "Photos Library API" for the project.
3. Save the downloaded JSON as ./client_secret.json next to this script.
4. First run opens a browser for consent; token cached at ./gdrive_token.json.

Usage
-----
    python gdrive_backup.py --dest ~/GDriveBackup
    python gdrive_backup.py --dest ~/GDriveBackup --include-photos
    python gdrive_backup.py --dest ~/GDriveBackup --dry-run         # list only
    python gdrive_backup.py --dest ~/GDriveBackup --report-only     # skip download, just analyze
    python gdrive_backup.py --dest ~/GDriveBackup --include-trashed

Cleanup report (written to <dest>/_cleanup_report.json and printed):
    - Duplicate files (same md5, different paths) — keep newest, delete rest
    - Files larger than --big-mb (default 100 MB)
    - Files not opened/modified in --stale-days (default 730 ≈ 2 years)
    - Items currently in Trash (candidates for permanent delete)
    - Google-native docs exported as Office formats (noted for reference)

Dependencies
------------
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib tqdm
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseDownload
except ImportError:
    sys.exit(
        "Missing deps. Install with:\n"
        "  pip install google-api-python-client google-auth-httplib2 "
        "google-auth-oauthlib tqdm"
    )

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **_):  # minimal fallback
        return it


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
]

TAKEOUT_URL = "https://takeout.google.com/"

# Google-native MIME → export format
EXPORT_MAP = {
    "application/vnd.google-apps.document":
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet":
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation":
        ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
    "application/vnd.google-apps.script": ("application/vnd.google-apps.script+json", ".json"),
}

SCRIPT_DIR = Path(__file__).resolve().parent
CLIENT_SECRET = SCRIPT_DIR / "client_secret.json"
TOKEN_FILE = SCRIPT_DIR / "gdrive_token.json"


# ---------------------------------------------------------------- auth

def authenticate():
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET.exists():
                sys.exit(f"Missing {CLIENT_SECRET}. See docstring for setup.")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return creds


# ---------------------------------------------------------------- drive listing

DRIVE_FIELDS = (
    "nextPageToken, files("
    "id, name, mimeType, parents, size, md5Checksum, "
    "modifiedTime, viewedByMeTime, createdTime, trashed, shortcutDetails, owners)"
)


def list_all_files(drive, include_trashed: bool):
    q = "" if include_trashed else "trashed = false"
    page_token = None
    while True:
        resp = drive.files().list(
            q=q or None,
            fields=DRIVE_FIELDS,
            pageSize=1000,
            pageToken=page_token,
            spaces="drive",
            includeItemsFromAllDrives=False,
            supportsAllDrives=False,
        ).execute()
        for f in resp.get("files", []):
            yield f
        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def build_path_index(files: list[dict], drive) -> dict[str, str]:
    """Map fileId -> relative POSIX path (folders resolved via parents)."""
    by_id = {f["id"]: f for f in files}

    # Fetch any missing parent folders (e.g. shared ancestors we don't own)
    missing = set()
    for f in files:
        for p in f.get("parents", []) or []:
            if p not in by_id:
                missing.add(p)
    for pid in missing:
        try:
            meta = drive.files().get(fileId=pid, fields="id,name,mimeType,parents").execute()
            by_id[pid] = meta
        except HttpError:
            pass

    def resolve(fid: str, seen=None) -> str:
        seen = seen or set()
        if fid in seen:
            return ""
        seen.add(fid)
        node = by_id.get(fid)
        if not node:
            return ""
        parents = node.get("parents") or []
        if not parents:
            return _safe(node["name"])
        return os.path.join(resolve(parents[0], seen), _safe(node["name"]))

    return {f["id"]: resolve(f["id"]) for f in files}


def _safe(name: str) -> str:
    bad = '<>:"/\\|?*\x00'
    out = "".join("_" if c in bad else c for c in name).strip().rstrip(".")
    return out or "unnamed"


# ---------------------------------------------------------------- download

def download_file(drive, file: dict, dest: Path, dry_run: bool) -> tuple[bool, str]:
    mime = file["mimeType"]
    if mime == "application/vnd.google-apps.folder":
        if not dry_run:
            dest.mkdir(parents=True, exist_ok=True)
        return True, "folder"
    if mime == "application/vnd.google-apps.shortcut":
        return True, "skip-shortcut"

    export = EXPORT_MAP.get(mime)
    if export:
        export_mime, ext = export
        target = dest.with_suffix(dest.suffix + ext if not dest.suffix.endswith(ext) else "")
    else:
        target = dest

    if target.exists() and target.stat().st_size > 0:
        return True, "cached"
    if dry_run:
        return True, "would-download"

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if export:
            request = drive.files().export_media(fileId=file["id"], mimeType=export[0])
        else:
            request = drive.files().get_media(fileId=file["id"])
        buf = io.FileIO(target, "wb")
        downloader = MediaIoBaseDownload(buf, request, chunksize=8 * 1024 * 1024)
        done = False
        while not done:
            _, done = downloader.next_chunk(num_retries=3)
        buf.close()
        return True, "downloaded"
    except HttpError as e:
        if target.exists():
            target.unlink(missing_ok=True)
        return False, f"error:{e.status_code}"


# ---------------------------------------------------------------- photos

def analyze_photos_dir(photos_root: Path, big_mb: int) -> dict:
    """Walk an unpacked Google Takeout 'Photos/' tree and flag dupes/big files.

    Takeout layout: <root>/Takeout/Google Photos/<Album>/*.{jpg,mp4,json}
    Same photo often appears in a named album AND "Photos from YYYY".
    Dedup is by content hash (md5) — json sidecars are ignored.
    """
    import hashlib

    big_bytes = big_mb * 1024 * 1024
    by_md5: dict[str, list[dict]] = defaultdict(list)
    big: list[dict] = []
    total = 0
    total_bytes = 0

    def md5(p: Path) -> str:
        h = hashlib.md5()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    files = [p for p in photos_root.rglob("*")
             if p.is_file() and p.suffix.lower() != ".json"]
    for p in tqdm(files, desc="Hashing photos", unit="file"):
        size = p.stat().st_size
        total += 1
        total_bytes += size
        rec = {"path": str(p), "size_mb": round(size / 1024 / 1024, 2)}
        if size >= big_bytes:
            big.append(rec)
        try:
            rec["md5"] = md5(p)
            by_md5[rec["md5"]].append(rec)
        except OSError as e:
            print(f"  hash fail {p}: {e}", file=sys.stderr)

    duplicates = []
    wasted = 0.0
    for h, group in by_md5.items():
        if len(group) < 2:
            continue
        duplicates.append({"md5": h, "keep": group[0], "delete": group[1:]})
        wasted += sum(r["size_mb"] for r in group[1:])

    big.sort(key=lambda r: r["size_mb"], reverse=True)
    return {
        "summary": {
            "total_files": total,
            "total_gb": round(total_bytes / 1024 / 1024 / 1024, 2),
            "duplicate_groups": len(duplicates),
            "duplicate_wasted_mb": round(wasted, 2),
            "big_files": len(big),
        },
        "duplicates": duplicates,
        "big_files": big[:200],
    }


def print_photos_guidance() -> None:
    print("\n" + "=" * 72)
    print("  Google Photos — use Google Takeout")
    print("=" * 72)
    print("  As of March 2025, Google restricted the Photos Library API so that")
    print("  third-party apps can only read media they themselves uploaded.")
    print("  A full-library backup via this script is no longer possible.")
    print()
    print(f"  Export your library instead at: {TAKEOUT_URL}")
    print("    1. Deselect all, then select only 'Google Photos'")
    print("    2. Choose album set (All albums) and format (original)")
    print("    3. Delivery: .tgz/.zip to your email or Drive")
    print("    4. Unpack into <dest>/Photos/ to co-locate with this backup")
    print("=" * 72)


# ---------------------------------------------------------------- cleanup analysis

def analyze(files: list[dict], paths: dict[str, str], big_mb: int, stale_days: int) -> dict:
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=stale_days)
    big_bytes = big_mb * 1024 * 1024

    by_md5: dict[str, list[dict]] = defaultdict(list)
    big: list[dict] = []
    stale: list[dict] = []
    trashed: list[dict] = []

    def parse(ts: str | None):
        if not ts:
            return None
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))

    for f in files:
        if f.get("mimeType") == "application/vnd.google-apps.folder":
            continue
        size = int(f.get("size") or 0)
        modified = parse(f.get("modifiedTime"))
        viewed = parse(f.get("viewedByMeTime"))
        last_touch = max(t for t in (modified, viewed) if t) if (modified or viewed) else None
        rec = {
            "id": f["id"], "path": paths.get(f["id"], f["name"]),
            "size_mb": round(size / 1024 / 1024, 2),
            "modified": f.get("modifiedTime"),
            "lastViewed": f.get("viewedByMeTime"),
            "md5": f.get("md5Checksum"),
        }
        if f.get("trashed"):
            trashed.append(rec)
            continue
        if f.get("md5Checksum"):
            by_md5[f["md5Checksum"]].append(rec)
        if size >= big_bytes:
            big.append(rec)
        if last_touch and last_touch < stale_cutoff and size > 1024 * 1024:
            stale.append(rec)

    duplicates = []
    wasted = 0
    for md5, group in by_md5.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: r["modified"] or "", reverse=True)
        keep, drop = group[0], group[1:]
        wasted += sum(r["size_mb"] for r in drop)
        duplicates.append({"md5": md5, "keep": keep, "delete": drop})

    big.sort(key=lambda r: r["size_mb"], reverse=True)
    stale.sort(key=lambda r: r["size_mb"], reverse=True)

    return {
        "generated": now.isoformat(),
        "summary": {
            "total_files": sum(1 for f in files if f.get("mimeType") != "application/vnd.google-apps.folder"),
            "duplicate_groups": len(duplicates),
            "duplicate_wasted_mb": round(wasted, 2),
            "big_files": len(big),
            "stale_files": len(stale),
            "trashed_files": len(trashed),
        },
        "duplicates": duplicates,
        "big_files": big[:200],
        "stale_files": stale[:200],
        "trashed_files": trashed,
    }


def print_report(r: dict, big_mb: int, stale_days: int) -> None:
    s = r["summary"]
    print("\n" + "=" * 72)
    print(f"  Cleanup Report — {r['generated']}")
    print("=" * 72)
    print(f"  Total files              : {s['total_files']}")
    print(f"  Duplicate groups         : {s['duplicate_groups']} "
          f"(~{s['duplicate_wasted_mb']} MB reclaimable)")
    print(f"  Files >= {big_mb} MB           : {s['big_files']}")
    print(f"  Stale (>{stale_days}d untouched) : {s['stale_files']}")
    print(f"  In Trash                 : {s['trashed_files']}")
    print("-" * 72)

    if r["big_files"]:
        print("\n  Top 10 largest files:")
        for f in r["big_files"][:10]:
            print(f"    {f['size_mb']:>9.2f} MB  {f['path']}")
    if r["duplicates"]:
        print("\n  Top 10 duplicate groups (keep newest, delete rest):")
        for g in r["duplicates"][:10]:
            print(f"    keep:   {g['keep']['path']}")
            for d in g["delete"]:
                print(f"    delete: {d['path']}  ({d['size_mb']} MB)")
    if r["trashed_files"]:
        print(f"\n  {len(r['trashed_files'])} file(s) in Trash — empty Trash in Drive UI to reclaim space.")
    print("=" * 72)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", required=True, help="Local backup root")
    ap.add_argument("--include-photos", action="store_true", help="Also pull Google Photos originals")
    ap.add_argument("--include-trashed", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="List only, no downloads")
    ap.add_argument("--report-only", action="store_true", help="Skip download, write report only")
    ap.add_argument("--big-mb", type=int, default=100)
    ap.add_argument("--stale-days", type=int, default=730)
    ap.add_argument("--photos-dir", help="Path to an unpacked Takeout Photos tree; "
                    "analyzes for duplicates and big files, writes _photos_cleanup_report.json")
    args = ap.parse_args()

    dest = Path(args.dest).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    creds = authenticate()
    drive = build("drive", "v3", credentials=creds)

    print("Listing Drive files...")
    files = list(list_all_files(drive, include_trashed=args.include_trashed))
    print(f"  {len(files)} items")

    print("Resolving folder paths...")
    paths = build_path_index(files, drive)

    drive_root = dest / "Drive"
    if not args.report_only:
        print("Downloading...")
        stats = defaultdict(int)
        for f in tqdm(files, unit="file"):
            rel = paths.get(f["id"]) or _safe(f["name"])
            target = drive_root / rel
            ok, status = download_file(drive, f, target, args.dry_run)
            stats[status] += 1
        print(f"  {dict(stats)}")

    if args.include_photos:
        print_photos_guidance()

    print("Analyzing for cleanup...")
    report = analyze(files, paths, args.big_mb, args.stale_days)
    report_path = dest / "_cleanup_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print_report(report, args.big_mb, args.stale_days)
    print(f"\nFull report: {report_path}")

    if args.photos_dir:
        photos_root = Path(args.photos_dir).expanduser().resolve()
        if not photos_root.exists():
            print(f"\n--photos-dir not found: {photos_root}", file=sys.stderr)
        else:
            print(f"\nAnalyzing Takeout photos at {photos_root}...")
            p_report = analyze_photos_dir(photos_root, args.big_mb)
            p_path = dest / "_photos_cleanup_report.json"
            p_path.write_text(json.dumps(p_report, indent=2))
            s = p_report["summary"]
            print("\n" + "=" * 72)
            print(f"  Photos Cleanup Report")
            print("=" * 72)
            print(f"  Total photo/video files : {s['total_files']} ({s['total_gb']} GB)")
            print(f"  Duplicate groups        : {s['duplicate_groups']} "
                  f"(~{s['duplicate_wasted_mb']} MB reclaimable)")
            print(f"  Files >= {args.big_mb} MB          : {s['big_files']}")
            if p_report["big_files"]:
                print("\n  Top 10 largest:")
                for f in p_report["big_files"][:10]:
                    print(f"    {f['size_mb']:>9.2f} MB  {f['path']}")
            print("=" * 72)
            print(f"Full photo report: {p_path}")


if __name__ == "__main__":
    main()
