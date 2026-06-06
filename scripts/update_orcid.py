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

# Output Paths
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data"
)
PUBLICATIONS_FILE = os.path.join(DATA_DIR, "publications.json")
GRANTS_FILE = os.path.join(DATA_DIR, "grants.json")

def get_nested(d, *keys, default=None):
    """Safely get nested dictionary keys that might be None or missing."""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key)
        else:
            return default
    return d if d is not None else default

def fetch_publications(session, headers):
    print(f"Fetching publications for ORCID: {ORCID_ID}...")
    
    works_url = f"{API_BASE}/{ORCID_ID}/works"
    try:
        response = session.get(works_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching works from ORCID API: {e}", file=sys.stderr)
        return False
        
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
        for ws in group.get("work-summary", []):
            put_code = ws.get("put-code")
            if not put_code:
                continue
                
            work_url = f"{API_BASE}/{ORCID_ID}/work/{put_code}"
            try:
                # Politeness sleep
                time.sleep(0.15)
                res = session.get(work_url, headers=headers, timeout=10)
                res.raise_for_status()
                detail = res.json()
            except Exception as e:
                print(f"Warning: Failed to fetch detail for put-code {put_code}: {e}", file=sys.stderr)
                continue
            
            # Extract title
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
                
            # Extract DOI
            ext_ids = get_nested(detail, "external-ids", "external-id", default=[])
            for ext_id in ext_ids:
                if ext_id.get("external-id-type") == "doi":
                    curr_doi = ext_id.get("external-id-value")
                    if curr_doi:
                        doi = curr_doi
                        if not url:
                            url = get_nested(ext_id, "external-id-url", "value")
                            
            # Extract contributors
            contribs = get_nested(detail, "contributors", "contributor", default=[])
            if contribs and not authors_list:
                authors_list = [
                    c["credit-name"]["value"] 
                    for c in contribs 
                    if isinstance(c, dict) and get_nested(c, "credit-name", "value")
                ]
                
        # Clean title
        if title:
            title = title.strip().rstrip(".,")
            
        # Fallback to DOI URL
        if doi and not url:
            url = f"https://doi.org/{doi}"
            
        # Fallback for authors
        authors_str = ", ".join(authors_list) if authors_list else "Halabi, Diego"
        
        if not title:
            continue
            
        parsed_publications.append({
            "title": title,
            "authors": authors_str,
            "journal": journal if journal else "Scientific Publication",
            "year": year if year else "N/A",
            "link": url if url else f"https://orcid.org/{ORCID_ID}"
        })
        
        print(f"Processed publication [{i+1}/{len(groups)}]: {title[:50]}...")

    # Sort: Year descending, then Title
    def sort_key(pub):
        yr = pub["year"]
        try:
            val = int(yr)
        except ValueError:
            val = 0
        return (-val, pub["title"].lower())
        
    parsed_publications.sort(key=sort_key)
    
    # Save
    with open(PUBLICATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(parsed_publications, f, indent=2, ensure_ascii=False)
    print(f"Successfully wrote {len(parsed_publications)} publications to {PUBLICATIONS_FILE}")
    return True

def fetch_grants(session, headers):
    print(f"\nFetching grants/funding for ORCID: {ORCID_ID}...")
    
    funding_url = f"{API_BASE}/{ORCID_ID}/fundings"
    try:
        response = session.get(funding_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching funding from ORCID API: {e}", file=sys.stderr)
        return False
        
    data = response.json()
    groups = data.get("group", [])
    print(f"Found {len(groups)} funding groups.")
    
    parsed_grants = []
    
    for i, group in enumerate(groups):
        # We merge info from the funding-summary elements in the group
        for summary in group.get("funding-summary", []):
            title = get_nested(summary, "title", "title", "value")
            f_type = summary.get("type", "award")
            
            # Translate ORCID types to readable format
            display_type = "Grant"
            if f_type == "salary-award":
                display_type = "Salary Award / Fellowship"
            elif f_type == "co-investigator":
                display_type = "Co-Investigator"
            elif f_type == "award":
                display_type = "Research Grant"
                
            start_year = get_nested(summary, "start-date", "year", "value")
            end_year = get_nested(summary, "end-date", "year", "value")
            
            org_name = get_nested(summary, "organization", "name")
            
            # Extract grant number
            grant_number = None
            ext_ids = get_nested(summary, "external-ids", "external-id", default=[])
            for ext_id in ext_ids:
                if ext_id.get("external-id-type") == "grant_number":
                    grant_number = ext_id.get("external-id-value")
                    
            url = get_nested(summary, "url", "value")
            
            # Fallback to general ORCID profile or ANID search if no URL
            if not url:
                url = f"https://orcid.org/{ORCID_ID}"
                
            if title:
                parsed_grants.append({
                    "title": title.strip().rstrip(".,"),
                    "type": display_type,
                    "start_year": start_year if start_year else "N/A",
                    "end_year": end_year if end_year else "Present",
                    "organization": org_name if org_name else "Scientific Institution",
                    "grant_number": grant_number if grant_number else "N/A",
                    "link": url
                })
                print(f"Processed grant [{i+1}/{len(groups)}]: {title[:50]}...")
                break # Only process one summary per group to avoid duplicate records
                
    # Sort grants: Start year descending (treat N/A as oldest)
    def sort_grants_key(grant):
        yr = grant["start_year"]
        try:
            val = int(yr)
        except ValueError:
            val = 0
        return (-val, grant["title"].lower())
        
    parsed_grants.sort(key=sort_grants_key)
    
    # Save
    with open(GRANTS_FILE, "w", encoding="utf-8") as f:
        json.dump(parsed_grants, f, indent=2, ensure_ascii=False)
    print(f"Successfully wrote {len(parsed_grants)} grants to {GRANTS_FILE}")
    return True

def main():
    session = requests.Session()
    headers = {"Accept": "application/json"}
    
    os.makedirs(DATA_DIR, exist_ok=True)
    
    pub_success = fetch_publications(session, headers)
    time.sleep(0.5) # respectful gap
    grant_success = fetch_grants(session, headers)
    
    if not (pub_success and grant_success):
        sys.exit(1)

if __name__ == "__main__":
    main()
