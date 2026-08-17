#!/usr/bin/env python3
"""
fetch_scholar_bib.py

Pulls every publication listed on a Google Scholar author profile and
writes them out as a single BibTeX (.bib) file.

Usage:
    python fetch_scholar_bib.py --scholar-id lTveB5cAAAAJ --out publications.bib

Notes:
- Uses the unofficial `scholarly` package (pip install scholarly), since
  Google Scholar has no official API.
- Google occasionally throttles/CAPTCHAs automated requests, especially
  from shared IPs (e.g. GitHub Actions runners). This script retries with
  backoff and can optionally route through free rotating proxies. If it
  still fails, it exits with a non-zero code so a scheduled job can flag
  the failure rather than silently publishing an empty file.
"""

import argparse
import sys
import time

from scholarly import scholarly, ProxyGenerator


def setup_proxy(use_proxy: bool) -> None:
    """Optionally route scholarly's requests through free rotating proxies.
    This helps avoid IP-based rate limiting on shared runners, but free
    proxies are unreliable -- if setup fails, we just continue without one.
    """
    if not use_proxy:
        return
    try:
        pg = ProxyGenerator()
        success = pg.FreeProxies()
        if success:
            scholarly.use_proxy(pg)
            print("Using a free rotating proxy for Scholar requests.")
        else:
            print("Could not set up a free proxy; continuing without one.")
    except Exception as e:
        print(f"Proxy setup failed ({e}); continuing without one.")


def fetch_publications_bibtex(scholar_id: str, max_retries: int = 3, delay: float = 2.0):
    """Fetch all publications for a Scholar author id and return a list of
    BibTeX entry strings."""
    author = scholarly.search_author_id(scholar_id)
    author = scholarly.fill(author, sections=["publications"])

    pubs = author.get("publications", [])
    print(f"Found {len(pubs)} publications on profile.")

    bib_entries = []
    for i, pub in enumerate(pubs, start=1):
        title = pub.get("bib", {}).get("title", "<unknown title>")
        for attempt in range(1, max_retries + 1):
            try:
                filled = scholarly.fill(pub)
                bibtex = scholarly.bibtex(filled)
                bib_entries.append(bibtex)
                print(f"[{i}/{len(pubs)}] OK: {title}")
                break
            except Exception as e:
                print(f"[{i}/{len(pubs)}] attempt {attempt} failed for '{title}': {e}")
                if attempt == max_retries:
                    print(f"[{i}/{len(pubs)}] giving up on: {title}")
                else:
                    time.sleep(delay * attempt)
        # Be polite / avoid tripping rate limits between requests
        time.sleep(delay)

    return bib_entries


def main():
    parser = argparse.ArgumentParser(description="Export Google Scholar publications to a .bib file")
    parser.add_argument("--scholar-id", required=True, help="Google Scholar user id, e.g. lTveB5cAAAAJ")
    parser.add_argument("--out", default="publications.bib", help="Output .bib file path")
    parser.add_argument("--use-proxy", action="store_true", help="Route requests through a free rotating proxy")
    args = parser.parse_args()

    setup_proxy(args.use_proxy)

    try:
        entries = fetch_publications_bibtex(args.scholar_id)
    except Exception as e:
        print(f"FATAL: could not fetch author profile: {e}", file=sys.stderr)
        sys.exit(1)

    if not entries:
        print("FATAL: no publications were successfully fetched; refusing to overwrite output.", file=sys.stderr)
        sys.exit(1)

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n\n".join(entries) + "\n")

    print(f"Wrote {len(entries)} entries to {args.out}")


if __name__ == "__main__":
    main()
