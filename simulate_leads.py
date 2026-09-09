"""
Simulated lead data for testing the Lead-Quality Engine.

Context: an Australian local-service client (Sydney plumber). Each lead carries
`_expected` = the ground-truth status we expect the engine to return, so the
test suite can assert precision. Timestamps are ISO strings.

Categories covered: qualified, unqualified, spam (several kinds), duplicate,
existing_customer, plus edge cases (call with no message, after-hours, etc.).
"""

CLIENT_CONFIG = {
    "service_area_terms": [
        "sydney", "parramatta", "bondi", "manly", "chatswood", "penrith",
        "nsw", "2000", "2150", "2026", "2088",
    ],
    "existing_customers": [
        {"email": "john.smith@gmail.com", "phone": "+61 400 111 222"},
        {"email": "acme.builders@bigpond.com", "phone": "0298765432"},
    ],
    "business_hours": (8, 18),
}


def get_labeled_leads() -> list[dict]:
    return [
        # ---------------- QUALIFIED (real, in-area, service intent) ----------
        {
            "lead_id": "L001", "timestamp": "2026-09-01T09:12:00",
            "name": "Sarah Jenkins", "email": "sarah.j@outlook.com",
            "phone": "+61 412 345 678", "location": "Bondi, NSW 2026",
            "message": "Hi, I have a burst pipe under my kitchen sink, need someone urgent today please. How much to come out?",
            "campaign": "Search - Emergency Plumber", "gclid": "abc123",
            "_expected": "qualified",
        },
        {
            "lead_id": "L002", "timestamp": "2026-09-01T14:03:00",
            "name": "Michael O'Brien", "email": "mobrien88@gmail.com",
            "phone": "0423 998 100", "location": "Parramatta",
            "message": "Looking to book a hot water system replacement quote this week.",
            "campaign": "Search - Hot Water", "gclid": "def456",
            "_expected": "qualified",
        },
        {
            "lead_id": "L003", "timestamp": "2026-09-02T18:40:00",
            "name": "Priya Nair", "email": "priya.nair@yahoo.com.au",
            "phone": "+61 405 220 331", "location": "Chatswood NSW",
            "message": "Blocked drain in the bathroom, water not draining. Can you fix tomorrow morning?",
            "campaign": "Search - Blocked Drain",
            "_expected": "qualified",
        },
        # A call lead: no message, valid phone, in-area -> should still qualify
        {
            "lead_id": "L004", "timestamp": "2026-09-02T11:20:00",
            "name": "Call - Manly", "email": "",
            "phone": "0490 123 456", "location": "Manly NSW 2088",
            "message": "", "channel": "call",
            "campaign": "Call - Emergency",
            "_expected": "qualified",
        },

        # ---------------- UNQUALIFIED (real but weak) ------------------------
        # Out of service area
        {
            "lead_id": "L010", "timestamp": "2026-09-01T10:05:00",
            "name": "Tom Baker", "email": "tbaker@gmail.com",
            "phone": "+61 411 777 888", "location": "Melbourne VIC 3000",
            "message": "Do you service Melbourne? Need a tap fixed.",
            "campaign": "Search - Plumber",
            "_expected": "unqualified",
        },
        # Job seeker
        {
            "lead_id": "L011", "timestamp": "2026-09-01T16:30:00",
            "name": "Dylan Cruz", "email": "dylancruz@gmail.com",
            "phone": "0432 100 200", "location": "Sydney",
            "message": "Hi, are you hiring apprentice plumbers? I'd like to apply for a position, I can send my resume.",
            "campaign": "Search - Plumber Near Me",
            "_expected": "unqualified",
        },
        # Thin, vague, no intent, no area confirmation
        {
            "lead_id": "L012", "timestamp": "2026-09-03T13:00:00",
            "name": "Kev", "email": "kev123@hotmail.com",
            "phone": "0400 555 010", "location": "",
            "message": "info",
            "campaign": "Display - Remarketing",
            "_expected": "unqualified",
        },

        # ---------------- SPAM ----------------------------------------------
        # SEO solicitation with link + keywords
        {
            "lead_id": "L020", "timestamp": "2026-09-01T03:11:00",
            "name": "Digital Growth", "email": "info@rankboost.biz",
            "phone": "", "location": "",
            "message": "We can improve your website SEO and get you to rank #1 with quality backlinks. Visit https://rankboost.biz for a free audit.",
            "_expected": "spam",
        },
        # Disposable email (hard)
        {
            "lead_id": "L021", "timestamp": "2026-09-01T04:22:00",
            "name": "asdf", "email": "xk9q@mailinator.com",
            "phone": "0000000000", "location": "",
            "message": "test",
            "_expected": "spam",
        },
        # Honeypot filled (hard) — bot
        {
            "lead_id": "L022", "timestamp": "2026-09-01T05:00:00",
            "name": "Robert", "email": "robert@gmail.com",
            "phone": "0412 000 111", "location": "Sydney",
            "message": "Need a plumber", "honeypot": "http://spam.link",
            "_expected": "spam",
        },
        # Gibberish + uncontactable (2 soft flags)
        {
            "lead_id": "L023", "timestamp": "2026-09-01T06:45:00",
            "name": "xkqzwbn", "email": "not-an-email",
            "phone": "123", "location": "",
            "message": "zzzxx",
            "_expected": "spam",
        },
        # Crypto/forex solicitation
        {
            "lead_id": "L024", "timestamp": "2026-09-02T02:30:00",
            "name": "Invest Pro", "email": "deals@fxpromo.com",
            "phone": "", "location": "",
            "message": "Amazing investment opportunity in crypto and forex, make money from home! Click here.",
            "_expected": "spam",
        },

        # ---------------- DUPLICATE -----------------------------------------
        # Original
        {
            "lead_id": "L030", "timestamp": "2026-09-01T09:00:00",
            "name": "Laura Kim", "email": "laura.kim@gmail.com",
            "phone": "+61 419 202 303", "location": "Penrith NSW 2750",
            "message": "Need a quote to install a new toilet, please call me.",
            "campaign": "Search - Toilet Install",
            "_expected": "qualified",
        },
        # Same person submits again 2 hours later (same email, formatted differently)
        {
            "lead_id": "L031", "timestamp": "2026-09-01T11:15:00",
            "name": "Laura Kim", "email": "Laura.Kim@gmail.com",
            "phone": "0419202303", "location": "Penrith",
            "message": "Just following up on my toilet install request.",
            "campaign": "Search - Toilet Install",
            "_expected": "duplicate",
        },
        # Same phone, different (typo) email — still a dupe on phone
        {
            "lead_id": "L032", "timestamp": "2026-09-01T15:45:00",
            "name": "Laura K", "email": "laurakim99@gmail.com",
            "phone": "+61 419 202 303", "location": "Penrith",
            "message": "Hello?",
            "_expected": "duplicate",
        },

        # ---------------- EXISTING CUSTOMER ---------------------------------
        {
            "lead_id": "L040", "timestamp": "2026-09-02T10:10:00",
            "name": "John Smith", "email": "john.smith@gmail.com",
            "phone": "0400 111 222", "location": "Sydney NSW 2000",
            "message": "Hi, it's John again — the mixer tap you installed is dripping, can you come back?",
            "campaign": "Search - Plumber",
            "_expected": "existing_customer",
        },
        {
            "lead_id": "L041", "timestamp": "2026-09-03T09:30:00",
            "name": "Acme Builders", "email": "accounts@acme.com.au",
            "phone": "02 9876 5432", "location": "Parramatta NSW 2150",
            "message": "Need you on our next site again, please quote rough-in for 3 bathrooms.",
            "campaign": "Search - Commercial Plumber",
            "_expected": "existing_customer",
        },
    ]


def get_leads_for_engine() -> list[dict]:
    """Same leads but with the _expected label stripped (as the engine sees them)."""
    out = []
    for lead in get_labeled_leads():
        out.append({k: v for k, v in lead.items() if k != "_expected"})
    return out


if __name__ == "__main__":
    leads = get_labeled_leads()
    print(f"{len(leads)} simulated leads")
    from collections import Counter
    print(Counter(l["_expected"] for l in leads))
