"""
Mock tools for the sample finance assistant scenario.

None of these touch a real system -- they exist purely to give the AGT
policy layer and MAF function middleware something concrete to intercept,
allow, deny, redact or escalate.
"""

_INVOICES = {
    "INV-1001": {"customer": "Contoso Ltd", "amount_usd": 4200.00, "status": "paid"},
    "INV-1004": {"customer": "Fabrikam Inc", "amount_usd": 15800.00, "status": "overdue"},
    "INV-1010": {"customer": "Northwind Traders", "amount_usd": 900.00, "status": "paid"},
}

# Mock GDPR consent-on-file record, keyed by customer name. Stands in for a
# real consent-management system this project doesn't have -- lets the
# compliance layer (governance/compliance_check.py, called from
# governance_pipeline.py) genuinely vary instead of the hardcoded
# consent_verified=True an earlier version of this project used, which made
# every compliance check trivially pass and never proved the check itself
# actually works. Northwind Traders deliberately has no record here, so a
# real GDPR-ART22 violation can be demonstrated by reading INV-1010.
CONSENT_ON_FILE = {
    "Contoso Ltd": True,
    "Fabrikam Inc": True,
    "Northwind Traders": False,
}


def has_consent(invoice_id: str) -> bool:
    invoice = _INVOICES.get(invoice_id)
    if invoice is None:
        return False
    return CONSENT_ON_FILE.get(invoice["customer"], False)


def read_invoice(invoice_id: str) -> dict:
    """Read a single invoice record. Marked sensitive -- triggers a DLP ratchet."""
    invoice = _INVOICES.get(invoice_id)
    if invoice is None:
        return {"error": f"No invoice found with id {invoice_id}"}
    return {"invoice_id": invoice_id, **invoice}


def query_database(query: str) -> dict:
    """Run a read-only lookup against the mock invoice table. Arguments are redacted in the audit log.

    Matches word-by-word: any word in the query that is also a substring of
    the invoice id or customer name counts as a match. A plain substring
    check in either single direction breaks depending on which string is
    longer -- e.g. checking "is query inside customer_name" fails for a
    short query like "Northwind", while "is customer_name inside query"
    fails for a longer, SQL-shaped query like
    "SELECT * FROM ... WHERE name LIKE '%Northwind%'" even though both
    obviously mean to search for "Northwind". See docs/implementation-notes.md
    for a real trace where this caused a false "no matches" result.
    """
    cleaned = query.lower()
    for ch in "'\"%;":
        cleaned = cleaned.replace(ch, " ")
    words = [w for w in cleaned.split() if len(w) > 2]
    matches = [
        {"invoice_id": k, **v}
        for k, v in _INVOICES.items()
        if any(w in k.lower() or w in v["customer"].lower() for w in words)
    ]
    return {"query": query, "matches": matches}


def send_email(to: str, body: str) -> dict:
    """Send a summary email. Blocked outright to an external address after a DLP ratchet has fired."""
    return {"sent_to": to, "body_preview": body[:120], "status": "sent"}


def drop_table(name: str) -> dict:
    """Deliberately destructive mock tool -- always denied by the block-destructive policy rule."""
    return {"table": name, "status": "dropped"}


TOOLS = [read_invoice, query_database, send_email, drop_table]
