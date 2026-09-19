import ipaddress
import re
import socket
import tldextract

_extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)
from urllib.parse import urlsplit, urlunsplit

SCORE_LIMITS = {"geographic_fit": 20, "technical_relevance": 20, "stem_alignment": 20,
                "company_capacity": 15, "education_connection": 10, "contactability": 10, "in_kind_value": 5}
JUNK = {"facebook.com", "linkedin.com", "youtube.com", "yelp.com", "wikipedia.org", "indeed.com", "instagram.com", "yellowpages.com", "thomasnet.com"}


def normalize_domain(url):
    parsed = urlsplit(url if "://" in url else "https://" + url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only HTTP company domains are allowed")
    host = (parsed.hostname or "").lower().rstrip(".").encode("idna").decode("ascii")
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host or parsed.username or parsed.password:
        raise ValueError("Not a company domain")
    try:
        ipaddress.ip_address(host)
        raise ValueError("IP addresses are not company domains")
    except ValueError as exc:
        if str(exc) == "IP addresses are not company domains":
            raise
    if host == "localhost" or host.endswith((".local", ".internal")):
        raise ValueError("Private domain rejected")
    extracted = _extract(host)
    if not extracted.suffix or not extracted.domain:
        raise ValueError("Unknown public suffix")
    return extracted.top_domain_under_public_suffix


def public_url(url, resolve=True):
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Only public HTTP URLs are allowed")
    if parts.port not in (None, 80, 443):
        raise ValueError("Nonstandard ports are not allowed")
    host = parts.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith((".local", ".internal")):
        raise ValueError("Private host rejected")
    addresses = [item[4][0] for item in socket.getaddrinfo(host, parts.port or 443)] if resolve else [host]
    for address in addresses:
        try:
            if not ipaddress.ip_address(address).is_global:
                raise ValueError("Private address rejected")
        except ValueError as exc:
            if str(exc) == "Private address rejected" or resolve:
                raise
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, ""))


def junk_domain(domain):
    return any(domain == item or domain.endswith("." + item) for item in JUNK)


def score_research(data, sources):
    for key, maximum in SCORE_LIMITS.items():
        value = data[key]
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
            raise ValueError("Invalid score: " + key)
    if not data["evidence"]:
        raise ValueError("Research needs supporting evidence")
    for evidence in data["evidence"]:
        source = sources.get(evidence["source_url"])
        quote = evidence["excerpt"].strip()
        if not source or len(quote) < 12 or quote not in source["text"]:
            raise ValueError("Evidence URL and exact excerpt must match supplied source")
    total = sum(data[key] for key in SCORE_LIMITS)
    data["overall_score"] = total
    data["tier"] = 1 if total >= 85 else 2 if total >= 70 else 3 if total >= 55 else 4
    data["suggested_cash_ask"] = {1: "$2,500-$5,000+", 2: "$1,000-$2,500", 3: "$500-$1,000", 4: "Not recommended yet"}[data["tier"]]
    return data


def validate_contacts(contacts, sources):
    for contact in contacts:
        source = sources.get(contact['source_url'])
        if not source or len(contact['excerpt'].strip()) < 12 or contact['excerpt'] not in source['text']:
            raise ValueError('Contact needs exact public source excerpt')
        for key in ('name', 'title', 'email', 'public_profile_url'):
            if contact[key] and contact[key] not in source['text']:
                raise ValueError('Contact field absent from source: ' + key)
    return contacts


def evidence_summary(evidence):
    return 'Source-matched model claims for human review:\n' + '\n'.join(
        item['claim'] + ' [' + item['source_url'] + ']' for item in evidence)


def filter_contacts(contacts, sources):
    """Discard whole unsupported contacts while preserving validated research."""
    accepted, warnings = [], []
    for index, contact in enumerate(contacts):
        try:
            validate_contacts([contact], sources)
        except ValueError as exc:
            warnings.append({'contact_index': index, 'reason': str(exc)})
        else:
            accepted.append(contact)
    return accepted, warnings


def research_queries(templates, company, domain):
    selected = [template for template in templates if any(term in template for term in ('Illinois', 'STEM education', 'community', 'FIRST Robotics', 'contact'))]
    return [template.format(company=company, domain=domain) for template in selected[:5]]


def daily_queries(queries, day, limit):
    if not queries:
        return []
    offset = day.toordinal() % len(queries)
    return [queries[(offset + index) % len(queries)] for index in range(min(limit, len(queries)))]


CURRENCY_RE = re.compile(r"\$\s?\d[\d,.]*\s?[kK]?\b|\b\d[\d,]*(?:\.\d+)?\s*dollars\b", re.I)

# The bare noun "donation(s)" also shows up in legitimate research evidence
# ("their CNC donation", "your donation of a CNC machine to Elgin Community
# College", "a strong history of charitable donations") -- the company's own
# giving, not the team asking for money. So instead of matching the noun on
# its own, DONATION_ASK_RE only fires on the grammatical shape of a request:
# a request verb ("asking for"/"seeking"/"requesting"/"hoping for"/
# "appreciate"/"consider") sitting right next to "donation(s)", or a donation
# explicitly directed "to our team"/"us"/"Team ####". "your donation of X to
# Y" and "history of ... donations" never match either shape.
DONATION_REQUEST_VERB_RE = r"(?:ask(?:ing)?\s+for|seek(?:ing)?|request(?:ing)?|hop(?:e|ing)\s+for|appreciat(?:e|ing)|consider(?:ing)?)"
DONATION_ASK_RE = (
    DONATION_REQUEST_VERB_RE + r"\s+(?:a\s+)?donations?\b",
    r"\bdonations?\s+to\s+(?:our\s+team\b|us\b|team\s*#?\d+)",
)
HARD_ASK_RE = tuple(re.compile(pattern, re.I) for pattern in (
    r"\bdonat(?:e|ing)\b", r"contribute\s+funds", r"sponsorship request",
    r"please sponsor", r"financial support", r"check made out",
    r"\bask(?:ing)?\s+for\s+(?:any\s+)?money\b", r"\bmoney\s+(?:now|yet)\b",
    r"\b(?:could|would|can|will)\b[^?.!\n]{0,80}\bsponsor\b",
    r"\bsponsor\s+(?:us|our team|team\s*#?\d+|frc\b)",
) + DONATION_ASK_RE)
SUBJECT_ASK_RE = tuple(re.compile(pattern, re.I) for pattern in (r"sponsorship request", r"\bdonation\b", r"fundraiser ask"))
FIRST_CONTACT_FUNDRAISING_RE = re.compile(
    r"\b(?:sponsor(?:ship|ing|ed)?|donat(?:e|ed|ing|ion|ions)|fundrais(?:e|er|ing)|money|cash|financial support)\b",
    re.I,
)
GENERIC_STYLE_RE = tuple(re.compile(pattern, re.I) for pattern in (
    r"\b(?:admire|admired)\b",
    r"\b(?:impressive|impressed)\b",
    r"\binnovative\b",
    r"\bindustry leaders?\b",
    r"\bincredibly relevant\b",
    r"\bshared interests?\b",
    r"\bmutual learning\b",
    r"\bstrategic alignment\b",
    r"\bsynergy\b",
    r"\bfit together\b",
    r"\bsupport (?:one another|each other)\b",
    r"\bhope this (?:email|message) finds you well\b",
    r"\bI know you(?:'re| are) busy\b",
    r"\bno pressure\b",
    r"\bat your earliest convenience\b",
    r"\bthank you for considering our request\b",
    r"\bwould love to\b",
))
VAGUE_GREETING_RE = re.compile(r"^\s*(?:hello|hi|hi there)\s*,", re.I)
FOLLOWUP_TIME_RE = re.compile(
    r"\b(?:last (?:week|month|Monday|Tuesday|Wednesday|Thursday|Friday)|yesterday|earlier this week|"
    r"on (?:Monday|Tuesday|Wednesday|Thursday|Friday)|\d{1,2}/\d{1,2}(?:/\d{2,4})?)\b",
    re.I,
)
MULTIPLE_CTA_RE = re.compile(
    r"\b(?:conversation|call|visit|tour|reply|email|advice|tip)\b[^?.!\n]{0,35}\bor\b[^?.!\n]{0,35}"
    r"\b(?:conversation|call|visit|tour|reply|email|advice|tip)\b",
    re.I,
)

# Signer identity is unknown at draft time; the model must sign with this exact
# placeholder rather than inventing a name or an ad-hoc bracketed stand-in.
SIGNATURE_TOKEN = "[Your Name]"
SIGNATURE_FIELDS = ("body", "followup_body")
SIGNATURE_BLOCK = "Best,\n[Your Name]\nExample Robotics Team | Team 0000\nExample High School"
PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]")
BROKEN_INTRO_RE = re.compile(r"my name is(?!\s*\[Your Name\])", re.I)

# Constructions where the WRITER (the team, plural, or the student writing on its
# behalf, singular) claims a prior relationship, familiarity, or duration of
# awareness with the company. Evidence-based claims about the company itself
# ("your 45 years in metal fabrication") and present-tense reactions to research
# ("we admire"/"I admire", "we noticed"/"I noticed", "I am interested") do not
# match any of these. Drafts are written by one student on the team's behalf, so
# first-person singular ("I", "I've") is just as common as plural ("we") and gets
# the same coverage.
#
# Built from a subject alternation and a verb alternation rather than spelling out
# every combination:
#   - SUBJECT_HAVE_RE: "we have"/"we've"/"I have"/"I've"/"I am"/"my team has"/
#     "our team has" + optional adverb + optional "been" + a relationship verb --
#     covers present-perfect and progressive forms ("we have followed", "I've
#     been watching", "my team has admired").
#   - SUBJECT_BARE_RE: bare "we"/"I" + a past-tense relationship verb -- covers
#     simple past ("we followed", "I worked with"). "followed"/"following"
#     exclude "... up" so a genuine follow-up note ("I'm following up on my
#     note", "we are following up") is never mistaken for a rapport claim.
RELATIONSHIP_VERB_RE = (
    r"(?:long |always |often )?(?:been\s+)?"
    r"(?:following(?!\s+up)|watching|admiring|admired|followed(?!\s+up)|watched|known|"
    r"worked with|partnered with|supported(?:\s+by)?)\b"
)
PAST_RELATIONSHIP_VERB_RE = (
    r"(?:followed(?!\s+up)|watched|admired|worked with|partnered with|were supported by)\b"
)
SUBJECT_HAVE_RE = r"\b(?:we(?:'ve| have)|I(?:'ve| have|\s+am)|(?:my|our) team has)\b"
SUBJECT_BARE_RE = r"\b(?:we|I)\b"

RAPPORT_RE = tuple(re.compile(pattern, re.I) for pattern in (
    r"\blong[- ]time admirers?\b",
    r"\bavid followers?\b",
    r"\bas a long[- ]time customer\b",
    r"\bwe are neighbors and\b",
    r"\bfor years,?\s+we(?:'ve| have)\b",
    SUBJECT_HAVE_RE + r"\s+" + RELATIONSHIP_VERB_RE,
    SUBJECT_BARE_RE + r"\s+" + PAST_RELATIONSHIP_VERB_RE,
))


def review_draft(draft):
    """Return a list of reasons the draft breaks relationship-first rules."""
    reasons = []
    for field in ("subject", "body", "linkedin_note", "followup_body"):
        value = draft.get(field) or ""
        if not value.strip():
            reasons.append(field + " is empty")
            continue
        if CURRENCY_RE.search(value):
            reasons.append(field + " states a dollar amount")
        if FIRST_CONTACT_FUNDRAISING_RE.search(value):
            reasons.append(field + " uses fundraising language in a first-contact sequence")
        if any(pattern.search(value) for pattern in HARD_ASK_RE):
            reasons.append(field + " makes a hard money ask")
        if any(pattern.search(value) for pattern in RAPPORT_RE):
            reasons.append(field + " invents a prior relationship or rapport with the company")
        if any(pattern.search(value) for pattern in GENERIC_STYLE_RE):
            reasons.append(field + " uses generic praise or corporate filler")
        if field in ("body", "linkedin_note") and VAGUE_GREETING_RE.search(value):
            reasons.append(field + " uses a vague greeting instead of a verified name or company team")
        if field in ("body", "linkedin_note", "followup_body") and value.count('?') > 1:
            reasons.append(field + " contains more than one question")
        if field in ("body", "followup_body") and MULTIPLE_CTA_RE.search(value):
            reasons.append(field + " offers multiple calls to action")
        if '!' in value:
            reasons.append(field + " uses an exclamation mark")
        for placeholder in PLACEHOLDER_RE.findall(value):
            if placeholder != SIGNATURE_TOKEN:
                reasons.append(field + " uses placeholder " + placeholder + " instead of [Your Name]")
        if field == "body" and BROKEN_INTRO_RE.search(value):
            reasons.append("body introduces the sender without the [Your Name] placeholder")
    for field in SIGNATURE_FIELDS:
        value = draft.get(field) or ""
        if value.strip() and SIGNATURE_TOKEN not in value:
            reasons.append(field + " is missing the [Your Name] signature")
        if value.strip() and not value.replace('\r\n', '\n').rstrip().endswith(SIGNATURE_BLOCK):
            reasons.append(field + " is missing the standard signature block")
    subject = draft.get("subject") or ""
    if any(pattern.search(subject) for pattern in SUBJECT_ASK_RE):
        reasons.append("subject leads with an ask")
    if '?' in subject:
        reasons.append("subject is phrased as a question")
    if len(subject) > 55:
        reasons.append("subject is longer than 55 characters")
    if re.search(r"\binquiry\b", subject, re.I):
        reasons.append("subject uses the generic word inquiry")
    body = draft.get("body") or ""
    body_before_signature = body.replace('\r\n', '\n').partition('\nBest,')[0]
    if len(re.findall(r"\b[\w'-]+\b", body_before_signature)) > 130:
        reasons.append("body is longer than 130 words before the signature")
    if len(draft.get("linkedin_note") or "") > 280:
        reasons.append("linkedin_note is longer than 280 characters")
    followup = draft.get("followup_body") or ""
    followup_before_signature = followup.replace('\r\n', '\n').partition('\nBest,')[0]
    if len(re.findall(r"\b[\w'-]+\b", followup_before_signature)) > 80:
        reasons.append("followup_body is longer than 80 words before the signature")
    if FOLLOWUP_TIME_RE.search(followup):
        reasons.append("followup_body invents when the earlier message was sent")
    return list(dict.fromkeys(reasons))  # dedupe, preserve order


def select_research_urls(homepage, results, domain, limit=8):
    owned, other = [], []
    seen = {homepage}
    for result in results:
        url = result['url']
        try:
            host = urlsplit(url).hostname or ''
            normalize_domain(url)
        except ValueError:
            continue
        if url in seen:
            continue
        seen.add(url)
        (owned if host.lower().rstrip('.') == domain or host.lower().rstrip('.').endswith('.' + domain) else other).append(url)
    return ([homepage] + owned + other)[:limit]
