"""
Full test suite for the Lead-Quality Engine.

Run:  python3 test_engine.py
Exits non-zero if any assertion fails. No external deps (plain asserts).
"""

import sys
from collections import Counter

from lead_quality_engine import (
    process_batch, summarize, normalize_email, normalize_phone,
    is_valid_phone, is_valid_email, looks_gibberish, detect_spam, CONFIG,
)
from simulate_leads import get_labeled_leads, get_leads_for_engine, CLIENT_CONFIG

PASS, FAIL = 0, 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(f"  ✗ {name} {('- ' + detail) if detail else ''}")


# ---------------------------------------------------------------------------
# 1. Unit tests — normalisation & validators
# ---------------------------------------------------------------------------
def test_units():
    check("gmail dots stripped",
          normalize_email("La.ura.Kim@gmail.com") == "laurakim@gmail.com",
          normalize_email("La.ura.Kim@gmail.com"))
    check("plus tag stripped",
          normalize_email("sarah+ads@outlook.com") == "sarah@outlook.com",
          normalize_email("sarah+ads@outlook.com"))
    check("non-gmail dots kept",
          normalize_email("first.last@outlook.com") == "first.last@outlook.com")
    check("phone +61 normalised to tail",
          normalize_phone("+61 419 202 303") == normalize_phone("0419202303"),
          f'{normalize_phone("+61 419 202 303")} vs {normalize_phone("0419202303")}')
    check("valid phone true", is_valid_phone("+61 412 345 678"))
    check("all-same-digit phone invalid", not is_valid_phone("0000000000"))
    check("short phone invalid", not is_valid_phone("123"))
    check("valid email true", is_valid_email("a@b.com"))
    check("invalid email false", not is_valid_email("not-an-email"))
    check("gibberish detected", looks_gibberish("xkqzwbn"))
    check("normal word not gibberish", not looks_gibberish("plumber"))


# ---------------------------------------------------------------------------
# 2. Detector-level: spam hard signals
# ---------------------------------------------------------------------------
def test_spam_detectors():
    _, _, _, is_spam = detect_spam(
        {"name": "x", "email": "a@mailinator.com", "phone": "0412000111", "message": "hi"},
        CONFIG)
    check("disposable email => spam (hard)", is_spam)

    _, _, _, is_spam = detect_spam(
        {"name": "Robert", "email": "robert@gmail.com", "phone": "0412000111",
         "message": "need a plumber", "honeypot": "x"}, CONFIG)
    check("honeypot => spam (hard)", is_spam)

    # single soft signal should NOT be spam on its own
    _, _, _, is_spam = detect_spam(
        {"name": "Real Person", "email": "real@gmail.com", "phone": "0412345678",
         "message": "check my site www.example.com"}, CONFIG)
    check("single soft signal (link) alone is not spam", not is_spam)


# ---------------------------------------------------------------------------
# 3. End-to-end: every labeled lead classifies as expected
# ---------------------------------------------------------------------------
def test_classification_matches_ground_truth():
    labeled = get_labeled_leads()
    expected = {l["lead_id"]: l["_expected"] for l in labeled}
    results = process_batch(get_leads_for_engine(), CLIENT_CONFIG)
    by_id = {r.lead_id: r for r in results}

    for lead_id, exp in expected.items():
        got = by_id[lead_id].status
        check(f"{lead_id} expected={exp}", got == exp, f"got={got}")

    # precision summary
    correct = sum(1 for lid, exp in expected.items() if by_id[lid].status == exp)
    acc = correct / len(expected)
    check(f"overall accuracy 100% ({correct}/{len(expected)})", acc == 1.0,
          f"{acc:.0%}")
    return results, expected, by_id


# ---------------------------------------------------------------------------
# 4. Evidence guarantee — no classification without a reason (Rule 4)
# ---------------------------------------------------------------------------
def test_every_classification_has_evidence():
    results = process_batch(get_leads_for_engine(), CLIENT_CONFIG)
    for r in results:
        if r.status in ("spam", "duplicate", "existing_customer"):
            check(f"{r.lead_id} {r.status} has a reason", len(r.reasons) >= 1,
                  "no reason attached")
        # qualified/unqualified must have a score-derived reason trail
        if r.status in ("qualified", "unqualified"):
            check(f"{r.lead_id} scored lead has reasons", len(r.reasons) >= 1)


# ---------------------------------------------------------------------------
# 5. Duplicate ordering — the ORIGINAL is kept, later ones flagged
# ---------------------------------------------------------------------------
def test_duplicate_keeps_original():
    results = process_batch(get_leads_for_engine(), CLIENT_CONFIG)
    by_id = {r.lead_id: r for r in results}
    check("L030 (first) is NOT duplicate", by_id["L030"].status != "duplicate",
          by_id["L030"].status)
    check("L031 (later, same email) IS duplicate", by_id["L031"].status == "duplicate")
    check("L032 (later, same phone) IS duplicate", by_id["L032"].status == "duplicate")
    check("L031 points back to original L030",
          by_id["L031"].evidence.get("duplicate_of") == "L030",
          str(by_id["L031"].evidence))


# ---------------------------------------------------------------------------
# 6. Summary math is internally consistent
# ---------------------------------------------------------------------------
def test_summary_consistency():
    results = process_batch(get_leads_for_engine(), CLIENT_CONFIG)
    s = summarize(results)
    c = s["counts"]
    check("counts sum to total",
          sum(c.values()) == s["total_leads"], str(c))
    check("real_leads = total - spam - duplicate",
          s["real_leads"] == s["total_leads"] - c["spam"] - c["duplicate"])
    check("lead_quality_pct in range", 0 <= s["lead_quality_pct"] <= 100)
    return s


def main():
    print("Running Lead-Quality Engine test suite...\n")
    test_units()
    test_spam_detectors()
    results, expected, by_id = test_classification_matches_ground_truth()
    test_every_classification_has_evidence()
    test_duplicate_keeps_original()
    s = test_summary_consistency()

    print(f"Ground-truth distribution: {dict(Counter(expected.values()))}")
    print(f"Engine summary: {s}\n")

    if FAILURES:
        print("FAILURES:")
        print("\n".join(FAILURES))
    print(f"\n{'='*50}")
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    print(f"{'='*50}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
