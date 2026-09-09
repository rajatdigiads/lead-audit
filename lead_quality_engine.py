"""
Lead-Quality Engine v1
======================
Classifies inbound Google Ads leads (form/call) into:
    spam | duplicate | existing_customer | qualified | unqualified

Design rules (Project Rule 4 — Evidence-Based AI):
  * Every classification is traceable to a concrete rule that fired.
  * No metric or reason is invented — each lead carries `reasons` (why) and
    `evidence` (the raw fields that triggered each rule).
  * All thresholds live in CONFIG so they are tunable per client, not hardcoded
    in logic.

No Google Ads API required. Input is a list of lead dicts (from a form webhook,
CRM export, or CSV). Output is a scored, explained result per lead + a batch
summary the AI/reporting layer can narrate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# CONFIG — everything tunable lives here (per-client override friendly)
# ---------------------------------------------------------------------------

CONFIG: dict[str, Any] = {
    # --- Spam ---
    # A lead is spam if it trips >= spam_flag_threshold soft signals,
    # OR any single hard signal fires.
    "spam_flag_threshold": 2,
    "disposable_email_domains": {
        "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
        "temp-mail.org", "yopmail.com", "trashmail.com", "sharklasers.com",
        "getnada.com", "dispostable.com", "fakeinbox.com", "throwawaymail.com",
    },
    "spam_message_keywords": [
        "seo service", "rank #1", "rank number 1", "backlink", "back link",
        "guest post", "buy now", "crypto", "bitcoin", "forex", "loan offer",
        "make money", "work from home", "increase your sales", "web design service",
        "we can improve your website", "marketing services", "dofollow",
        "casino", "viagra", "click here", "limited time offer", "investment opportunity",
    ],
    # keywords that mean this is NOT a customer (job seeker / solicitation)
    "job_seeker_keywords": [
        "job", "hiring", "vacancy", "resume", "cv", "career", "apply for",
        "position", "internship", "employment",
    ],
    "solicitation_keywords": [
        "partnership", "wholesale", "supplier", "collaborate", "reseller",
        "affiliate", "sponsor", "b2b offer",
    ],
    # --- Qualification ---
    "service_intent_keywords": [
        "quote", "book", "booking", "appointment", "install", "installation",
        "repair", "fix", "replace", "emergency", "urgent", "asap", "leak",
        "broken", "not working", "service", "need", "help", "estimate", "price",
        "how much", "available", "today", "tomorrow", "come out", "call me",
    ],
    "qualified_score_threshold": 55,      # >= this => qualified
    "sales_ready_score_threshold": 75,    # >= this => flagged sales-ready
    # weights for qualification scoring (start at 50 neutral, add/subtract)
    "weights": {
        "base": 50,
        "service_intent_kw": 12,          # per hit, capped
        "service_intent_cap": 24,
        "in_service_area": 15,
        "out_of_service_area": -20,
        "valid_phone": 8,
        "valid_email": 6,
        "message_present": 6,
        "message_too_short": -10,         # < min_message_len non-empty
        "job_seeker": -35,
        "solicitation": -30,
        "after_hours": 3,                 # tiny positive (intent to be called back)
    },
    "min_message_len": 8,
    # --- Duplicate ---
    "duplicate_window_days": 30,          # same contact within N days = duplicate
    # --- Business context (per client) ---
    "service_area_terms": [],             # e.g. ["sydney","parramatta","2000","nsw"]
    "existing_customers": [],             # list of {"email":..,"phone":..}
    "business_hours": (8, 18),            # local hours considered "in hours"
}

# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

VALID_STATUSES = (
    "spam", "duplicate", "existing_customer", "qualified", "unqualified"
)


@dataclass
class LeadResult:
    lead_id: str
    status: str
    quality_score: int                    # 0-100 (qualification score)
    is_sales_ready: bool = False
    flags: list[str] = field(default_factory=list)      # short machine flags
    reasons: list[str] = field(default_factory=list)    # human-readable "why"
    evidence: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def normalize_email(email: str | None) -> str:
    if not email:
        return ""
    email = email.strip().lower()
    if "@" not in email:
        return email
    local, _, domain = email.partition("@")
    # strip +tags
    local = local.split("+", 1)[0]
    # gmail ignores dots in local part
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
    return f"{local}@{domain}"


def normalize_phone(phone: str | None) -> str:
    """Return the last 9 significant digits (handles +61 / 0 prefixes)."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return ""
    # drop leading country code / trunk zero, keep the significant tail
    return digits[-9:] if len(digits) >= 9 else digits


def email_domain(email: str | None) -> str:
    if not email or "@" not in email:
        return ""
    return email.strip().lower().rsplit("@", 1)[-1]


_VOWELS = set("aeiou")


def looks_gibberish(text: str | None) -> bool:
    """Heuristic: a token with a long consonant run and no vowels is likely junk.
    Conservative — only fires on clearly random strings (e.g. 'xkqzwbn')."""
    if not text:
        return False
    for token in re.findall(r"[a-zA-Z]{5,}", text.lower()):
        if not (_VOWELS & set(token)):
            return True
        # 5+ consonants in a row
        if re.search(r"[bcdfghjklmnpqrstvwxyz]{5,}", token):
            return True
    return False


def is_valid_phone(phone: str | None) -> bool:
    d = re.sub(r"\D", "", phone or "")
    if len(d) < 8 or len(d) > 15:
        return False
    if len(set(d)) == 1:                       # 0000000000, 1111111111
        return False
    if d in ("1234567890", "0123456789", "1234567891"):
        return False
    return True


def is_valid_email(email: str | None) -> bool:
    if not email:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def _contains_any(text: str, keywords: Iterable[str]) -> list[str]:
    t = (text or "").lower()
    return [kw for kw in keywords if kw in t]


# ---------------------------------------------------------------------------
# Detectors — each returns (fired_flags, reasons, evidence)
# ---------------------------------------------------------------------------

def detect_spam(lead: dict, cfg: dict) -> tuple[list[str], list[str], dict, bool]:
    flags, reasons, evidence = [], [], {}
    hard = False
    name = str(lead.get("name", "") or "")
    email = str(lead.get("email", "") or "")
    phone = str(lead.get("phone", "") or "")
    message = str(lead.get("message", "") or "")

    # HARD: honeypot field filled (bots fill hidden fields)
    if lead.get("honeypot"):
        flags.append("honeypot_filled")
        reasons.append("Hidden honeypot field was filled — automated bot submission.")
        evidence["honeypot"] = lead.get("honeypot")
        hard = True

    # HARD: disposable / temp email domain
    dom = email_domain(email)
    if dom and dom in cfg["disposable_email_domains"]:
        flags.append("disposable_email")
        reasons.append(f"Disposable/temp email domain: {dom}")
        evidence["email_domain"] = dom
        hard = True

    # SOFT: link in message
    if re.search(r"https?://|www\.", message.lower()):
        flags.append("link_in_message")
        reasons.append("Message contains a URL — typical of SEO/backlink spam.")
        evidence["link"] = re.findall(r"(https?://\S+|www\.\S+)", message.lower())

    # SOFT: spam keywords
    kw = _contains_any(message, cfg["spam_message_keywords"])
    if kw:
        flags.append("spam_keywords")
        reasons.append(f"Solicitation/spam keywords in message: {', '.join(kw)}")
        evidence["spam_keywords"] = kw
        # 2+ distinct solicitation keywords is a clear spam pattern on its own.
        if len(kw) >= 2:
            flags.append("multi_spam_keywords")
            reasons.append("Multiple solicitation keywords — clear spam/solicitation pattern.")

    # SOFT: gibberish name or email local part
    if looks_gibberish(name) or looks_gibberish(email.split("@")[0]):
        flags.append("gibberish")
        reasons.append("Name or email looks randomly generated.")
        evidence["gibberish_source"] = name or email

    # SOFT: name empty or contains digits
    if not name.strip():
        flags.append("no_name")
        reasons.append("No name provided.")
    elif re.search(r"\d", name):
        flags.append("name_has_digits")
        reasons.append("Name contains digits.")
        evidence["name"] = name

    # SOFT: invalid phone AND invalid email (uncontactable)
    if not is_valid_phone(phone) and not is_valid_email(email):
        flags.append("uncontactable")
        reasons.append("Neither a valid phone nor a valid email was provided.")
        evidence["phone"] = phone
        evidence["email"] = email

    soft_count = len([f for f in flags if f not in ("honeypot_filled", "disposable_email")])
    is_spam = hard or (soft_count >= cfg["spam_flag_threshold"])
    return flags, reasons, evidence, is_spam


def match_existing_customer(lead: dict, cfg: dict) -> tuple[bool, list[str], dict]:
    reasons, evidence = [], {}
    ne = normalize_email(lead.get("email"))
    npnum = normalize_phone(lead.get("phone"))
    for cust in cfg.get("existing_customers", []):
        ce = normalize_email(cust.get("email"))
        cp = normalize_phone(cust.get("phone"))
        if (ne and ne == ce) or (npnum and npnum == cp):
            reasons.append("Contact matches an existing customer record.")
            evidence["matched_on"] = "email" if ne == ce else "phone"
            evidence["matched_value"] = ne if ne == ce else npnum
            return True, reasons, evidence
    return False, reasons, evidence


def score_qualification(lead: dict, cfg: dict) -> tuple[int, list[str], list[str], dict, bool]:
    w = cfg["weights"]
    flags, reasons, evidence = [], [], {}
    score = w["base"]
    message = str(lead.get("message", "") or "")
    phone = str(lead.get("phone", "") or "")
    email = str(lead.get("email", "") or "")
    location = str(lead.get("location", "") or "")

    # service intent
    hits = _contains_any(message, cfg["service_intent_keywords"])
    if hits:
        pts = min(len(hits) * w["service_intent_kw"], w["service_intent_cap"])
        score += pts
        flags.append("service_intent")
        reasons.append(f"Service-intent language ({', '.join(hits[:5])}) [+{pts}]")
        evidence["intent_keywords"] = hits

    # service area
    area_terms = cfg.get("service_area_terms", [])
    if area_terms:
        blob = f"{location} {message}".lower()
        in_area = any(t.lower() in blob for t in area_terms)
        if in_area:
            score += w["in_service_area"]
            flags.append("in_service_area")
            reasons.append(f"Location is within the service area [+{w['in_service_area']}]")
        else:
            score += w["out_of_service_area"]
            flags.append("out_of_service_area")
            reasons.append(f"No service-area match found [{w['out_of_service_area']}]")

    # contactability
    if is_valid_phone(phone):
        score += w["valid_phone"]
        reasons.append(f"Valid phone number [+{w['valid_phone']}]")
    if is_valid_email(email):
        score += w["valid_email"]
        reasons.append(f"Valid email [+{w['valid_email']}]")

    # message presence / length
    if message.strip():
        if len(message.strip()) < cfg["min_message_len"]:
            score += w["message_too_short"]
            flags.append("thin_message")
            reasons.append(f"Message very short [{w['message_too_short']}]")
        else:
            score += w["message_present"]
    # (empty message: no bonus, no penalty — calls often have none)

    # job seeker / solicitation
    js = _contains_any(message, cfg["job_seeker_keywords"])
    if js:
        score += w["job_seeker"]
        flags.append("job_seeker")
        reasons.append(f"Looks like a job enquiry ({', '.join(js)}) [{w['job_seeker']}]")
        evidence["job_seeker_keywords"] = js
    sol = _contains_any(message, cfg["solicitation_keywords"])
    if sol:
        score += w["solicitation"]
        flags.append("solicitation")
        reasons.append(f"Looks like a sales/partnership pitch ({', '.join(sol)}) [{w['solicitation']}]")
        evidence["solicitation_keywords"] = sol

    # after hours (minor)
    ts = _parse_ts(lead.get("timestamp"))
    if ts:
        lo, hi = cfg["business_hours"]
        if not (lo <= ts.hour < hi):
            score += w["after_hours"]

    score = max(0, min(100, score))

    # Local-service gate: if a service area is configured and this lead shows no
    # in-area signal, it cannot be 'qualified' — you can't dispatch a job to an
    # unknown or wrong location. Score is capped just below the qualified line so
    # it routes to manual area check instead of the sales-ready queue.
    if "out_of_service_area" in flags:
        cap = cfg["qualified_score_threshold"] - 1
        if score > cap:
            score = cap
            reasons.append("Capped below qualified: service area not confirmed.")

    is_sales_ready = score >= cfg["sales_ready_score_threshold"]
    return score, flags, reasons, evidence, is_sales_ready


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def classify_lead(lead: dict, cfg: dict, seen: dict) -> LeadResult:
    """Classify a single lead. `seen` tracks already-processed contacts for
    duplicate detection and is mutated as a side effect (call in time order)."""
    lead_id = str(lead.get("lead_id") or lead.get("id") or id(lead))
    all_flags: list[str] = []
    all_reasons: list[str] = []
    evidence: dict[str, Any] = {}

    # 1) Spam (highest priority — pollutes everything downstream)
    sflags, sreasons, sevidence, is_spam = detect_spam(lead, cfg)
    all_flags += sflags
    if is_spam:
        return LeadResult(lead_id, "spam", 0, False, sflags, sreasons, sevidence, dict(lead))

    # 2) Duplicate (within window)
    ne = normalize_email(lead.get("email"))
    npnum = normalize_phone(lead.get("phone"))
    ts = _parse_ts(lead.get("timestamp")) or datetime.min
    window = timedelta(days=cfg["duplicate_window_days"])
    dup_key = None
    for key in (("email", ne), ("phone", npnum)):
        kind, val = key
        if val and val in seen.get(kind, {}):
            prev_ts, prev_id = seen[kind][val]
            if ts - prev_ts <= window:
                dup_key = (kind, val, prev_id)
                break
    # record this contact for future dupes (first occurrence wins as "original")
    for kind, val in (("email", ne), ("phone", npnum)):
        if val:
            seen.setdefault(kind, {}).setdefault(val, (ts, lead_id))
    if dup_key:
        kind, val, prev_id = dup_key
        return LeadResult(
            lead_id, "duplicate", 0, False,
            ["duplicate"],
            [f"Same {kind} as earlier lead {prev_id} within {cfg['duplicate_window_days']} days."],
            {"duplicate_of": prev_id, "matched_on": kind, "value": val},
            dict(lead),
        )

    # 3) Existing customer
    is_existing, ereasons, eevidence = match_existing_customer(lead, cfg)
    if is_existing:
        # still score it so the agency knows repeat-intent quality
        qscore, _, _, _, _ = score_qualification(lead, cfg)
        return LeadResult(
            lead_id, "existing_customer", qscore, False,
            ["existing_customer"], ereasons, eevidence, dict(lead),
        )

    # 4) Qualify
    qscore, qflags, qreasons, qevidence, sales_ready = score_qualification(lead, cfg)
    all_flags += qflags
    all_reasons += qreasons
    evidence.update(qevidence)
    status = "qualified" if qscore >= cfg["qualified_score_threshold"] else "unqualified"
    return LeadResult(lead_id, status, qscore, sales_ready, all_flags, all_reasons, evidence, dict(lead))


def process_batch(leads: list[dict], cfg: dict | None = None) -> list[LeadResult]:
    cfg = {**CONFIG, **(cfg or {})}
    # process in timestamp order so "first seen" is the true original
    ordered = sorted(leads, key=lambda l: _parse_ts(l.get("timestamp")) or datetime.min)
    seen: dict = {}
    return [classify_lead(l, cfg, seen) for l in ordered]


def summarize(results: list[LeadResult]) -> dict[str, Any]:
    total = len(results)
    counts = {s: 0 for s in VALID_STATUSES}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    real_leads = total - counts["spam"] - counts["duplicate"]      # what the client actually got
    new_business = counts["qualified"] + counts["unqualified"]      # excludes existing customers
    qualified = counts["qualified"]
    sales_ready = sum(1 for r in results if r.is_sales_ready)
    lead_quality_pct = round(100 * real_leads / total, 1) if total else 0.0
    qualified_rate = round(100 * qualified / real_leads, 1) if real_leads else 0.0
    return {
        "total_leads": total,
        "counts": counts,
        "real_leads": real_leads,
        "spam_and_duplicate": counts["spam"] + counts["duplicate"],
        "new_business_leads": new_business,
        "qualified": qualified,
        "sales_ready": sales_ready,
        "lead_quality_pct": lead_quality_pct,        # valid / total
        "qualified_rate_pct": qualified_rate,        # qualified / valid
    }
