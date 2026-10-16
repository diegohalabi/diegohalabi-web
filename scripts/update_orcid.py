#!/usr/bin/env python3
"""Sync publications and grants from the ORCID public API.

Writes data/publications.json and data/grants.json, and renders both lists as
static HTML into index.html and es/index.html (between the ORCID:* markers) so
the content is indexable without JavaScript.

Safety: nothing is written unless every request succeeded and the new lists
pass sanity checks (non-empty, no sudden drop). Set ALLOW_SHRINK=1 to accept a
legitimate large reduction (e.g. after removing works from ORCID).
"""
import html
import json
import os
import re
import sys
import time
import unicodedata

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configuration
DEFAULT_ORCID_ID = "0000-0002-1474-8066"
ORCID_ID = os.environ.get("ORCID_ID", DEFAULT_ORCID_ID)
API_BASE = "https://pub.orcid.org/v3.0"
ALLOW_SHRINK = os.environ.get("ALLOW_SHRINK") == "1"
MAX_SHRINK_RATIO = 0.8  # abort if a list drops below 80% of its previous size

# Output Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
PUBLICATIONS_FILE = os.path.join(DATA_DIR, "publications.json")
GRANTS_FILE = os.path.join(DATA_DIR, "grants.json")
# Pages that receive the rendered lists, by language
INDEX_FILES = {
    "en": os.path.join(BASE_DIR, "index.html"),
    "es": os.path.join(BASE_DIR, "es", "index.html"),
}

# How the site owner's name is displayed (and highlighted) in author lists
SELF_AUTHOR = "Halabi D"

# Corrections for names that ORCID sources store wrongly (applied after formatting)
AUTHOR_FIXES = {
    "Elena Silva M": "Silva ME",
    "Roberto Salazar-Petres E": "Salazar-Petres ER",
    "Richter Hans GH": "Richter HG",
    "Muoz C": "Muñoz C",
}

# Canonical journal names for sources that store them inconsistently
JOURNAL_FIXES = {
    "journal oral of research": "Journal of Oral Research",
    "journal of physiology": "The Journal of Physiology",
    "journal of physiology-london": "The Journal of Physiology",
    "nutricion hospitalaria": "Nutrición Hospitalaria",
    "revista odontológica mexicana órgano oficial de la facultad de odontología unam": "Revista Odontológica Mexicana",
}

# Funders renamed since the grants were awarded (CONICYT became ANID in 2020)
ORG_FIXES = {
    "Comisión Nacional de Investigación Científica y Tecnológica": "ANID (formerly CONICYT)",
    "Fondo de Fomento al Desarrollo Científico y Tecnológico": "ANID (formerly CONICYT)",
}

# What ORCID does not store: the owner's role and titles in both languages (from the CV)
GRANT_DETAILS = {
    "FONDECYT 11190711": {"role": "pi"},
    "FONDEF ID17AM0043": {
        "role": "postdoc",
        "title_en": "The fountain of youth: development of an antioxidant, anti-inflammatory and neuroregenerative supplement derived from hops for brain rejuvenation",
    },
    "VIDCA-INID210009-03": {
        "role": "associate",
        "title_es": "Melatonina en bayas chilenas: un regalo cronobiótico de la naturaleza",
    },
}

# Grants missing from ORCID (from the CV). Skipped automatically once ORCID lists the same number.
EXTRA_GRANTS = [
    {
        "title": "Melatonin in Chilean berries: a chronobiotic gift of nature",
        "type": "Grant",
        "start_year": "2022",
        "end_year": "2023",
        "organization": "Universidad Austral de Chile (VIDCA)",
        "grant_number": "VIDCA-INID210009-03",
        "link": f"https://orcid.org/{ORCID_ID}",
    },
]

TITLE_SMALL_WORDS = {"a", "an", "and", "de", "del", "for", "in", "la", "of", "on", "the", "y"}


class SyncError(Exception):
    pass


def get_nested(d, *keys, default=None):
    """Safely get nested dictionary keys that might be None or missing."""
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key)
        else:
            return default
    return d if d is not None else default


def strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def format_author_name(name):
    """Formats an author name to 'LastName Initials' format (e.g., 'Soto M', 'Poblete MT')."""
    name = name.strip()
    if not name:
        return ''

    # Correct common spelling typos
    if 'erhenfeld' in name.lower():
        name = name.replace('Erhenfeld', 'Ehrenfeld').replace('erhenfeld', 'ehrenfeld')

    # Case A: If name has a comma (standard ORCID format 'LastName, FirstName MiddleName')
    if ',' in name:
        parts = name.split(',')
        last = parts[0].strip()
        firsts = parts[1].strip()
        firsts_clean = firsts.replace('.', ' ').replace('-', ' ')
        subparts = [w.strip() for w in firsts_clean.split() if w.strip()]
        initials = ''.join([w[0].upper() for w in subparts if w])
        formatted = f'{last} {initials}'
    else:
        # Case B: If no comma (Spanish names or regular First Last format)
        words = [w.strip() for w in name.split() if w.strip()]
        if len(words) <= 1:
            formatted = name
        elif len(words) == 2 or '-' in words[-1]:
            # e.g., 'Diego Halabi' -> 'Halabi D'
            # e.g., 'María José Céspedes-Barrientos' -> 'Céspedes-Barrientos MJ'
            formatted = f'{words[-1]} ' + ''.join(w[0].upper() for w in words[:-1])
        else:
            # e.g., 'Camila Ruiz Chaura' -> 'Ruiz Chaura C'
            # e.g., 'Helmuth Daniel Muñoz Martínez' -> 'Muñoz Martínez HD'
            formatted = f'{words[-2]} {words[-1]} ' + ''.join(w[0].upper() for w in words[:-2])

    formatted = AUTHOR_FIXES.get(formatted, formatted)

    # Unify every variant of the owner's name ('Halabí-Robles D', 'Halab D', ...)
    if re.match(r'^halab', strip_accents(formatted).lower()) and formatted.endswith(' D'):
        return SELF_AUTHOR
    return formatted


def normalize_journal(journal):
    if not journal:
        return "Scientific Publication"
    journal = journal.strip()
    if re.match(r'^https?://', journal):
        if 'isrctn' in journal.lower():
            return "ISRCTN Registry (trial registration)"
        return re.sub(r'^https?://(www\.)?', '', journal).strip('/')
    fixed = JOURNAL_FIXES.get(journal.lower())
    if fixed:
        return fixed
    if journal.isupper():
        words = journal.lower().split()
        journal = ' '.join(
            w if (i > 0 and w in TITLE_SMALL_WORDS) else w[:1].upper() + w[1:]
            for i, w in enumerate(words)
        )
    return journal


def is_aggregator_url(url):
    return bool(re.search(r'publons\.com|scopus\.com', url or '', re.I))


def make_session():
    session = requests.Session()
    retry = Retry(total=4, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch_publications(session, headers):
    print(f"Fetching publications for ORCID: {ORCID_ID}...")

    works_url = f"{API_BASE}/{ORCID_ID}/works"
    try:
        response = session.get(works_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise SyncError(f"Error fetching works from ORCID API: {e}")

    groups = response.json().get("group", [])
    print(f"Found {len(groups)} publication groups. Fetching details for each...")

    parsed_publications = []
    failed_put_codes = []

    for i, group in enumerate(groups):
        title = None
        journal = None
        year = None
        doi = None
        urls = []
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
                print(f"Error: Failed to fetch detail for put-code {put_code}: {e}", file=sys.stderr)
                failed_put_codes.append(put_code)
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

            # Collect URLs (the best one is chosen after the loop)
            curr_url = get_nested(detail, "url", "value")
            if curr_url:
                urls.append(curr_url)

            # Extract DOI
            ext_ids = get_nested(detail, "external-ids", "external-id", default=[])
            for ext_id in ext_ids:
                if ext_id.get("external-id-type") == "doi" and ext_id.get("external-id-value"):
                    doi = doi or ext_id["external-id-value"].strip()

            # Extract contributors, preferring the source with the most complete names
            contribs = get_nested(detail, "contributors", "contributor", default=[])
            raw_authors = [
                c["credit-name"]["value"]
                for c in contribs
                if isinstance(c, dict) and get_nested(c, "credit-name", "value")
            ]
            if len(raw_authors) > len(authors_list) or (
                raw_authors and len(raw_authors) == len(authors_list)
                and sum(map(len, raw_authors)) > sum(map(len, authors_list))
            ):
                authors_list = raw_authors

        if not title:
            continue

        # Clean title
        title = title.strip().rstrip(".,")

        # Link priority: DOI, then a publisher URL, then aggregators, then ORCID
        if doi:
            link = f"https://doi.org/{doi.lower()}"
        else:
            direct = [u for u in urls if not is_aggregator_url(u)]
            link = (direct or urls or [f"https://orcid.org/{ORCID_ID}"])[0]

        authors = [format_author_name(a) for a in authors_list]
        parsed_publications.append({
            "title": title,
            "authors": ", ".join(authors) if authors else SELF_AUTHOR,
            "journal": normalize_journal(journal),
            "year": year if year else "N/A",
            "link": link,
        })

        print(f"Processed publication [{i+1}/{len(groups)}]: {title[:50]}...")

    if failed_put_codes:
        raise SyncError(f"{len(failed_put_codes)} work detail request(s) failed: {failed_put_codes}")

    # Sort: Year descending, then Title
    def sort_key(pub):
        try:
            val = int(pub["year"])
        except ValueError:
            val = 0
        return (-val, pub["title"].lower())

    parsed_publications.sort(key=sort_key)
    return parsed_publications


def fetch_grants(session, headers):
    print(f"\nFetching grants/funding for ORCID: {ORCID_ID}...")

    funding_url = f"{API_BASE}/{ORCID_ID}/fundings"
    try:
        response = session.get(funding_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise SyncError(f"Error fetching funding from ORCID API: {e}")

    groups = response.json().get("group", [])
    print(f"Found {len(groups)} funding groups.")

    parsed_grants = []

    for i, group in enumerate(groups):
        for summary in group.get("funding-summary", []):
            title = get_nested(summary, "title", "title", "value")
            f_type = summary.get("type", "award")

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

            grant_number = None
            ext_ids = get_nested(summary, "external-ids", "external-id", default=[])
            for ext_id in ext_ids:
                if ext_id.get("external-id-type") == "grant_number":
                    grant_number = ext_id.get("external-id-value")

            url = get_nested(summary, "url", "value")

            if not url:
                url = f"https://orcid.org/{ORCID_ID}"

            if title:
                parsed_grants.append({
                    "title": title.strip().rstrip(".,"),
                    "type": display_type,
                    "start_year": start_year if start_year else "N/A",
                    "end_year": end_year if end_year else "Present",
                    "organization": ORG_FIXES.get(org_name, org_name) if org_name else "Scientific Institution",
                    "grant_number": grant_number if grant_number else "N/A",
                    "link": url
                })
                print(f"Processed grant [{i+1}/{len(groups)}]: {title[:50]}...")
                break

    listed = {g["grant_number"] for g in parsed_grants}
    parsed_grants += [dict(g) for g in EXTRA_GRANTS if g["grant_number"] not in listed]
    for grant in parsed_grants:
        grant.update(GRANT_DETAILS.get(grant["grant_number"], {}))

    # Sort grants
    def sort_grants_key(grant):
        try:
            val = int(grant["start_year"])
        except ValueError:
            val = 0
        return (-val, grant["title"].lower())

    parsed_grants.sort(key=sort_grants_key)
    return parsed_grants


def check_not_shrunk(label, new_items, path):
    """Refuse to replace existing data with an empty or much smaller list."""
    try:
        with open(path, encoding="utf-8") as f:
            old_count = len(json.load(f))
    except (OSError, ValueError):
        old_count = 0
    if old_count and not new_items:
        raise SyncError(f"ORCID returned 0 {label} (previously {old_count}); refusing to overwrite.")
    if old_count and len(new_items) < old_count * MAX_SHRINK_RATIO and not ALLOW_SHRINK:
        raise SyncError(
            f"{label} dropped from {old_count} to {len(new_items)}; refusing to overwrite "
            f"(set ALLOW_SHRINK=1 if this is intended)."
        )


# -------------------------------------------------------------------------
# Static HTML rendering (keep markup in sync with js/site.js, which filters it)
# -------------------------------------------------------------------------
LABELS = {
    "en": {
        "view_paper": "View Paper",
        "count": lambda n: f"{n} item{'s' if n != 1 else ''} found",
        "present": "Present",
        "roles": {"pi": "Principal Investigator", "associate": "Associate Investigator", "postdoc": "Postdoctoral Researcher"},
        "orgs": {},
        "journals": {},
    },
    "es": {
        "view_paper": "Ver artículo",
        "count": lambda n: f"{n} resultado{'s' if n != 1 else ''}",
        "present": "Actualidad",
        "roles": {"pi": "Investigador Principal", "associate": "Investigador Asociado", "postdoc": "Investigador Postdoctoral"},
        "orgs": {"ANID (formerly CONICYT)": "ANID (ex CONICYT)"},
        "journals": {"ISRCTN Registry (trial registration)": "Registro ISRCTN (registro de ensayo)"},
    },
}


def esc(value):
    return html.escape(str(value if value is not None else ''), quote=True)


def safe_url(value):
    url = str(value or '').strip()
    return url if re.match(r'^(https?:|mailto:)', url, re.I) else '#'


def render_authors(authors):
    escaped = esc(authors)
    return re.sub(
        rf'(?<![\w-]){re.escape(esc(SELF_AUTHOR))}(?![\w-])',
        f'<strong class="font-semibold text-slate-900 dark:text-slate-200">{esc(SELF_AUTHOR)}</strong>',
        escaped,
    )


def render_publication(pub, idx, lang):
    L = LABELS[lang]
    journal = L["journals"].get(pub['journal'], pub['journal'])
    search_text = strip_accents(f"{pub['title']} {pub['authors']} {journal}").lower()
    doi_match = re.search(r'doi\.org/(10\.\d{4,9}/[-._;()/:A-Z0-9]+)', pub['link'], re.I)
    doi_html = ''
    if doi_match:
        doi = esc(doi_match.group(1))
        doi_html = f"""
                <span class="hidden sm:inline-block text-[10px] font-mono text-slate-500 dark:text-slate-500 truncate max-w-[140px]" title="DOI: {doi}">DOI: {doi}</span>"""
    return f"""          <article data-pub data-year="{esc(pub['year'])}" data-search="{esc(search_text)}" class="p-6 hover:bg-slate-100/60 dark:hover:bg-slate-900/30 transition-colors duration-200 flex flex-col sm:flex-row items-start justify-between gap-4">
            <div class="space-y-2 flex-1">
              <div class="flex items-center space-x-2">
                <span class="text-xs font-mono text-teal-700 dark:text-accentTeal font-bold px-1.5 py-0.5 rounded border border-teal-600/10 dark:border-accentTeal/20 bg-teal-50 dark:bg-accentTeal/5">{esc(pub['year'])}</span>
                <span class="text-xs font-mono text-slate-400 dark:text-slate-500">#{idx}</span>
              </div>
              <h3 class="text-base font-bold text-slate-900 dark:text-white">{esc(pub['title'])}</h3>
              <p class="text-xs text-slate-600 dark:text-slate-400 font-sans leading-relaxed">{render_authors(pub['authors'])}</p>
              <p class="text-xs text-slate-500 dark:text-slate-400 italic">{esc(journal)}</p>
            </div>
            <div class="flex sm:flex-col items-center sm:items-end gap-2 w-full sm:w-auto">
              <a href="{esc(safe_url(pub['link']))}" target="_blank" rel="noopener noreferrer" class="flex-1 sm:flex-initial text-center px-3 py-1.5 text-xs font-medium rounded bg-slate-100 border border-slate-200 hover:border-teal-600 text-slate-700 hover:text-teal-600 dark:bg-slate-900 dark:border-brandDarkBorder dark:hover:border-accentTeal dark:text-slate-400 dark:hover:text-accentTeal transition-colors flex items-center justify-center gap-1.5 shadow-sm" aria-label="{esc(L['view_paper'])}: {esc(pub['title'])}">
                <span>{esc(L['view_paper'])}</span>
                <i class="fa-solid fa-arrow-up-right-from-square text-[10px]" aria-hidden="true"></i>
              </a>{doi_html}
            </div>
          </article>"""


def render_grant(grant, lang):
    L = LABELS[lang]
    title = grant.get(f"title_{lang}") or grant['title']
    end_year = L["present"] if grant['end_year'] == "Present" else grant['end_year']
    org = L["orgs"].get(grant['organization'], grant['organization'])
    role = L["roles"].get(grant.get("role"), "")
    role_html = f"""
              <p class="text-xs font-semibold text-teal-700 dark:text-accentTeal">{esc(role)}</p>""" if role else ""
    return f"""          <article class="p-6 hover:bg-slate-100/60 dark:hover:bg-slate-900/30 transition-colors duration-200">
            <div class="space-y-2">
              <div class="flex flex-wrap items-center gap-2">
                <span class="text-xs font-mono text-teal-700 dark:text-accentTeal font-bold px-1.5 py-0.5 rounded border border-teal-600/10 dark:border-accentTeal/20 bg-teal-50 dark:bg-accentTeal/5">{esc(grant['start_year'])} - {esc(end_year)}</span>
                <span class="text-xs font-mono text-slate-400 dark:text-slate-500">{esc(grant['grant_number'])}</span>
              </div>
              <h3 class="text-base font-bold text-slate-900 dark:text-white">{esc(title)}</h3>{role_html}
              <p class="text-xs text-slate-600 dark:text-slate-400 font-sans leading-relaxed">{esc(org)}</p>
            </div>
          </article>"""


def replace_block(source, name, content, path):
    pattern = re.compile(rf'(<!-- ORCID:{name}:START -->)(.*?)(<!-- ORCID:{name}:END -->)', re.S)
    if not pattern.search(source):
        raise SyncError(f"Marker ORCID:{name} not found in {os.path.relpath(path, BASE_DIR)}")
    return pattern.sub(lambda m: f"{m.group(1)}{content}{m.group(3)}", source, count=1)


def render_index(publications, grants):
    for lang, path in INDEX_FILES.items():
        with open(path, encoding="utf-8") as f:
            source = f.read()

        pubs_html = "\n" + "\n".join(render_publication(p, i + 1, lang) for i, p in enumerate(publications)) + "\n          "
        grants_html = "\n" + "\n".join(render_grant(g, lang) for g in grants) + "\n          "

        source = replace_block(source, "PUBLICATIONS", pubs_html, path)
        source = replace_block(source, "GRANTS", grants_html, path)
        source = replace_block(source, "PUB_COUNT", LABELS[lang]["count"](len(publications)), path)

        with open(path, "w", encoding="utf-8") as f:
            f.write(source)


def write_json(path, items):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    session = make_session()
    headers = {"Accept": "application/json"}

    os.makedirs(DATA_DIR, exist_ok=True)

    try:
        publications = fetch_publications(session, headers)
        time.sleep(0.5)
        grants = fetch_grants(session, headers)
        check_not_shrunk("publications", publications, PUBLICATIONS_FILE)
        check_not_shrunk("grants", grants, GRANTS_FILE)
        render_index(publications, grants)
    except SyncError as e:
        print(f"\nSync aborted, existing data left untouched: {e}", file=sys.stderr)
        sys.exit(1)

    write_json(PUBLICATIONS_FILE, publications)
    write_json(GRANTS_FILE, grants)
    print(f"\nWrote {len(publications)} publications and {len(grants)} grants, and updated the pages")


if __name__ == "__main__":
    main()
