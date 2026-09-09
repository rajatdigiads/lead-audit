"""
Shared IO helpers: CSV column auto-detection + row->lead mapping.
Used by both load_csv.py (CLI) and app.py (Streamlit) so the mapping logic
lives in exactly one place.
"""

# engine field -> accepted header names (normalised: lowercased, non-alnum stripped)
AUTODETECT = {
    "name":      ["name", "fullname", "yourname", "firstname", "contactname", "leadname"],
    "email":     ["email", "emailaddress", "youremail", "e-mail"],
    "phone":     ["phone", "phonenumber", "mobile", "contactnumber", "tel", "telephone", "yourphone"],
    "message":   ["message", "comments", "enquiry", "inquiry", "yourmessage", "details", "notes", "description"],
    "timestamp": ["timestamp", "date", "datetime", "created", "createdat", "submittedon", "datesubmitted", "entrydate"],
    "campaign":  ["campaign", "utmcampaign", "campaignname", "adcampaign"],
    "gclid":     ["gclid", "clickid"],
    "location":  ["location", "suburb", "city", "postcode", "area", "region", "state"],
    "lead_id":   ["lead_id", "id", "entryid", "leadid", "recordid"],
    "honeypot":  ["honeypot", "hp", "hidden"],
}

ENGINE_FIELDS = list(AUTODETECT.keys())


def norm(h: str) -> str:
    return "".join(c for c in str(h).lower() if c.isalnum())


def build_column_map(headers, manual_override=None):
    """Return {engine_field: actual_header}. manual_override wins."""
    manual_override = manual_override or {}
    norm_headers = {norm(h): h for h in headers}
    col_map = {}
    for field, aliases in AUTODETECT.items():
        if field in manual_override and manual_override[field] in headers:
            col_map[field] = manual_override[field]
            continue
        for alias in aliases:
            if norm(alias) in norm_headers:
                col_map[field] = norm_headers[norm(alias)]
                break
    return col_map


def rows_to_leads(rows, col_map):
    """rows = list of dicts (csv.DictReader-style). Returns engine-ready leads."""
    leads = []
    for i, row in enumerate(rows):
        lead = {}
        for field, header in col_map.items():
            val = row.get(header)
            lead[field] = (str(val).strip() if val is not None else "")
        if not lead.get("lead_id"):
            lead["lead_id"] = f"row{i+1}"
        leads.append(lead)
    return leads
