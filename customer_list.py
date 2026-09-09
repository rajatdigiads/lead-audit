"""
Ecommerce / B2B Customer-List profile.
Segments a customer database by REAL value (spend + orders), surfaces
campaign-actionable insights (Customer Match seed, exclusions, geo, B2B/B2C,
Pareto, AOV, data gaps), and builds Google Ads Customer Match export files.

No Google Ads API needed — reads a CSV export (Shopify/CRM/ecom platform).
"""
from __future__ import annotations
import re
import pandas as pd
import numpy as np

# --- flexible column detection ---------------------------------------------
EC_AUTODETECT = {
    "email":   ["email", "emailaddress", "customeremail"],
    "phone":   ["phone", "defaultaddressphone", "mobile", "phonenumber"],
    "first":   ["firstname", "first"],
    "last":    ["lastname", "last"],
    "company": ["company", "defaultaddresscompany", "companyname"],
    "city":    ["city", "defaultaddresscity", "town"],
    "state":   ["province", "state", "provincecode", "defaultaddressprovincecode", "region"],
    "country": ["country", "countrycode", "defaultaddresscountrycode"],
    "zip":     ["zip", "postcode", "postalcode", "defaultaddresszip"],
    "spent":   ["totalspent", "amountspent", "lifetimevalue", "ltv", "revenue"],
    "orders":  ["totalorders", "orderscount", "orders", "numberoforders"],
    "date":    ["lastorderdate", "orderdate", "lastorder", "mostrecentorder"],
}

CONFIG = {
    "vip_min_orders": 5,
    "spend_top_pct": 0.90,     # spenders at/above this percentile also count VIP
}


def _norm(h): return "".join(c for c in str(h).lower() if c.isalnum())


def detect_columns(headers, override=None):
    override = override or {}
    nh = {_norm(h): h for h in headers}
    cmap = {}
    for field, aliases in EC_AUTODETECT.items():
        if field in override and override[field] in headers:
            cmap[field] = override[field]; continue
        for a in aliases:
            if _norm(a) in nh:
                cmap[field] = nh[_norm(a)]; break
    return cmap


def _num(series):
    return pd.to_numeric(series.astype(str).str.replace(r"[^0-9.\-]", "", regex=True),
                         errors="coerce").fillna(0)


def is_junk(name, email):
    name = (name or "").lower().strip()
    e = (email or "").lower()
    if not name and not e:
        return True
    if re.search(r"(.)\1\1", name):                 # aaaa
        return True
    if re.search(r"[bcdfghjklmnpqrstvwxyz]{5,}", name):
        return True
    for t in ("test@", "@example", "asdf", "sdfsdf", "qwerty", "noreply@"):
        if t in e or t in name:
            return True
    return False


def analyze(df: pd.DataFrame, cmap: dict, cfg: dict | None = None):
    cfg = {**CONFIG, **(cfg or {})}
    g = lambda f: df[cmap[f]] if f in cmap else pd.Series([""] * len(df))

    email = g("email").astype(str)
    # coalesce across ALL phone-like columns (exports often split phone across two)
    phone_cols = [h for h in df.columns if "phone" in _norm(h) or "mobile" in _norm(h)]
    if phone_cols:
        phone = df[phone_cols].astype(str).apply(
            lambda row: next((v.strip() for v in row if v and v.strip()), ""), axis=1)
    else:
        phone = g("phone").astype(str)
    first = g("first").astype(str); last = g("last").astype(str)
    name = (first + " " + last).str.strip()
    company = g("company").astype(str).str.strip()
    spent = _num(g("spent")); orders = _num(g("orders"))
    city = g("city").astype(str).str.strip()
    state = g("state").astype(str).str.strip()

    has_phone = phone.str.strip() != ""
    is_b2b = company != ""
    spend_thresh = spent[spent > 0].quantile(cfg["spend_top_pct"]) if (spent > 0).any() else np.inf

    seg = []
    reasons = []
    for i in range(len(df)):
        if is_junk(name.iat[i], email.iat[i]):
            seg.append("junk"); reasons.append("gibberish/test record — purge"); continue
        o, s = orders.iat[i], spent.iat[i]
        if o >= cfg["vip_min_orders"] or (s >= spend_thresh and s > 0):
            seg.append("vip"); reasons.append(f"{int(o)} orders · ${s:,.0f} — top customer")
        elif o >= 2:
            seg.append("repeat"); reasons.append(f"{int(o)} orders · ${s:,.0f} — repeat buyer")
        elif o == 1:
            seg.append("one_time"); reasons.append(f"1 order · ${s:,.0f} — win back to 2nd order")
        else:
            seg.append("prospect"); reasons.append("signed up, never purchased — remarket/exclude")

    out = df.copy()
    out["segment"] = seg
    out["why"] = reasons
    out["_spent"] = spent
    out["_orders"] = orders
    out["_email"] = email.str.lower().str.strip()
    out["_phone"] = phone.str.strip()
    out["_name"] = name
    out["_city"] = city
    out["_state"] = state
    out["_company"] = company

    # duplicates: same full name with 2+ distinct emails
    nm = out[out["_name"] != ""].groupby(out["_name"].str.lower())["_email"].nunique()
    dup_people = int((nm >= 2).sum())

    buyers = out[out["_orders"] > 0]
    rev = buyers["_spent"].sort_values(ascending=False)
    top20 = int(np.ceil(len(rev) * 0.2))
    pareto = round(100 * rev.head(top20).sum() / rev.sum(), 1) if rev.sum() else 0
    aov = round(buyers["_spent"].sum() / buyers["_orders"].sum(), 2) if buyers["_orders"].sum() else 0

    counts = out["segment"].value_counts().to_dict()
    geo_top = (buyers.groupby("_state")["_spent"].sum().sort_values(ascending=False).head(5)
               if "state" in cmap else pd.Series(dtype=float))
    city_top = (buyers.groupby("_city")["_spent"].sum().sort_values(ascending=False).head(5)
                if "city" in cmap else pd.Series(dtype=float))

    summary = {
        "total_records": len(out),
        "segments": counts,
        "buyers": int((out["_orders"] > 0).sum()),
        "prospects_never_bought": int((out["_orders"] == 0).sum()) - counts.get("junk", 0)
                                  if False else int(counts.get("prospect", 0)),
        "repeat_or_vip": int(counts.get("repeat", 0) + counts.get("vip", 0)),
        "junk_records": int(counts.get("junk", 0)),
        "total_revenue": round(out["_spent"].sum(), 2),
        "avg_order_value": aov,
        "top20pct_revenue_share": pareto,
        "b2b_with_company": int(is_b2b.sum()),
        "missing_phone": int((~has_phone).sum()),
        "duplicate_people_by_name": dup_people,
        "has_dates": "date" in cmap,
    }
    return out, summary, geo_top, city_top


# --- Google Ads Customer Match exports --------------------------------------
# Google Ads Customer Match template columns (UI accepts plaintext & hashes on
# upload; normalise anyway: lowercase email, trim).
CM_COLUMNS = ["Email", "Phone Number", "First Name", "Last Name", "Country", "Zip"]


def customer_match_frame(out: pd.DataFrame, cmap: dict, segments: list[str]) -> pd.DataFrame:
    sub = out[out["segment"].isin(segments)]
    def col(f): return sub[cmap[f]] if f in cmap else ""
    df = pd.DataFrame({
        "Email": sub["_email"],
        "Phone Number": sub["_phone"],
        "First Name": col("first"),
        "Last Name": col("last"),
        "Country": col("country"),
        "Zip": col("zip"),
    })
    # keep rows with at least an email or phone
    df = df[(df["Email"].astype(str).str.strip() != "") | (df["Phone Number"].astype(str).str.strip() != "")]
    return df.reset_index(drop=True)


def build_exports(out: pd.DataFrame, cmap: dict):
    """Returns dict of {name: dataframe} ready to download for Google Ads."""
    return {
        "customer_match_high_value": customer_match_frame(out, cmap, ["vip", "repeat"]),
        "customer_match_win_back": customer_match_frame(out, cmap, ["one_time"]),
        "exclusion_never_purchased": customer_match_frame(out, cmap, ["prospect"]),
    }
