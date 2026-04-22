The fixes in py2notebook.py:

Added _trim_blank_lines() — strips leading/trailing blank lines from every cell and collapses 3+ consecutive blanks to 2
Updated make_cell() — runs the trim on all cell sources and ensures the last line always ends with \n
if __name__ auto-split — now treated as a cell boundary like def/class, so it gets its own cell
flush() simplified — delegates all newline cleanup to make_cell()

Fixed for new seperate line breaks for markdown tags in python script, _fix_markdown_newlines now does in py2notebook.py:

Indented blocks (4+ spaces or tab) get wrapped in ``` code fences — so the usage examples now render as a proper code block instead of running together
Consecutive non-blank lines get two trailing spaces ( \n) which forces a <br> line break in Markdown — so multi-line descriptions like "Fetches regular and premium... / near a given ZIP code..." show on separate lines
Blank lines are left as-is since they already create paragraph breaks in Markdown


Created gdrive_backup.py and updated README.md.
What it does:

Paginates drive.files.list, resolves full folder paths (fetches missing shared ancestors), and mirrors everything under <dest>/Drive/.
Exports Google-native docs → .docx/.xlsx/.pptx/.png; downloads binaries in 8 MB chunks with resume (skips existing non-empty files).
--include-photos pulls Google Photos originals (=d / =dv) into Photos/YYYY/YYYY-MM-DD/.
Writes _cleanup_report.json and prints a summary covering:
Duplicates by md5Checksum (keeps newest, lists others + reclaimable MB)
Big files ≥ --big-mb (default 100)
Stale items untouched for --stale-days (default 730, using max of modifiedTime/viewedByMeTime)
Trashed items (candidates for permanent delete)
Setup required: create an OAuth Desktop client in Google Cloud, enable Drive API + Photos Library API, drop client_secret.json next to the script. --dry-run and --report-only let you try it safely.