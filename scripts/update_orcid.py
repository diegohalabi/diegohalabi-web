#!/usr/bin/env python3
import os
import sys
import json
import time
import requests

# Configuration
DEFAULT_ORCID_ID = "0000-0002-1474-8066"
ORCID_ID = os.environ.get("ORCID_ID", DEFAULT_ORCID_ID)
API_BASE = "https://pub.orcid.org/v3.0"
OUTPUT_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "publications.json"
)

def get_nested(d, *keys, default=None):
    """Safely get nested dictionary keys that might be None or missing."""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key)
        else:
            return default
    return d if d is not None else default

def fetch_publications():
    print(f"Fetching publications for ORCID: {ORCID_ID}...")
    session = requests.Session()
    headers = {"Accept": "application/json"}
    
    # 1. Fetch the list of all works (summaries)
    works_url = f"{API_BASE}/{ORCID_ID}/works"
    try:
        response = session.get(works_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching works from ORCID API: {e}", file=sys.stderr)
        sys.exit(1)
        
    data = response.json()
    groups = data.get("group", [])
    print(f"Found {len(groups)} publication groups. Fetching details for each...")
    
    parsed_publications = []
    
    for i, group in enumerate(groups):
        title = None
        journal = None
        year = None
        doi = None
        url = None
        authors_list = []
        
        # A group contains summaries of duplicate or related entries for a single work.
        # We merge information across all versions in the group to get the most complete metadata.
        for ws in group.get("work-summary", []):
            put_code = ws.get("put-code")
            if not put_code:
                continue
                
            work_url = f"{API_BASE}/{ORCID_ID}/work/{put_code}"
            try:
                # Politeness sleep to prevent rate limiting
                time.sleep(0.15)
                res = session.get(work_url, headers=headers, timeout=10)
                res.raise_for_status()
                detail = res.json()
            except Exception as e:
                print(f"Warning: Failed to fetch detail for put-code {put_code}: {e}", file=sys.stderr)
                continue
            
            # Extract title (prefer longest/most complete title)
            curr_title = get_nested(detail, "title", "title", "value")
            if curr_title and (not title or len(curr_title) > len(title)):
                title = curr_title
                
            # Extract journal-title
            curr_journal = get_nested(detail, "journal-title", "value")
            if curr_journal and not journal:
                journal = curr_journal
                
            # Extract publication year
            curr_year = get_nested(detail, "publication-date", "year", "value")
            if curr_year and not year:
                year = curr_year
                    
            # Extract URL
            curr_url = get_nested(detail, "url", "value")
            if curr_url and not url:
                url = curr_url
                
            # Extract DOI and check for URL fallback
            ext_ids = get_nested(detail, "external-ids", "external-id", default=[])
            for ext_id in ext_ids:
                if ext_id.get("external-id-type") == "doi":
                    curr_doi = ext_id.get("external-id-value")
                    if curr_doi:
                        doi = curr_doi
                        if not url:
                            url = get_nested(ext_id, "external-id-url", "value")
                            
            # Extract contributors (authors)
            contribs = get_nested(detail, "contributors", "contributor", default=[])
            if contribs and not authors_list:
                authors_list = [
                    c["credit-name"]["value"] 
                    for c in contribs 
                    if isinstance(c, dict) and get_nested(c, "credit-name", "value")
                ]
                
        # Clean title: Remove trailing periods or commas if present
        if title:
            title = title.strip().rstrip(".,")
            
        # Fallback to DOI-based URL if URL not resolved
        if doi and not url:
            url = f"https://doi.org/{doi}"
            
        # Fallback for authors if ORCID contributors list was empty across all sources.
        # Since this is Dr. Diego Halabi's profile, we default to "Halabi, Diego" if none found.
        authors_str = ", ".join(authors_list) if authors_list else "Halabi, Diego"
        
        # Skip entry if it doesn't even have a title
        if not title:
            continue
            
        parsed_publications.append({
            "title": title,
            "authors": authors_str,
            "journal": journal if journal else "Scientific Publication",
            "year": year if year else "N/A",
            "link": url if url else f"https://orcid.org/{ORCID_ID}"
        })
        
        print(f"Processed [{i+1}/{len(groups)}]: {title[:50]}...")

    # Sort publications: Year descending (treat N/A as oldest), then by Title alphabetically
    def sort_key(pub):
        yr = pub["year"]
        try:
            val = int(yr)
        except ValueError:
            val = 0
        return (-val, pub["title"].lower())
        
    parsed_publications.sort(key=sort_key)
    
    # Save to JSON
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(parsed_publications, f, indent=2, ensure_ascii=False)
        
    print(f"\nSuccessfully wrote {len(parsed_publications)} publications to {OUTPUT_FILE}")

if __name__ == "__main__":
    fetch_publications()
