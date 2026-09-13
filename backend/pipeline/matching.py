"""Name matching for brand -> entity adjudication.

Substring matching is the obvious approach and it is wrong. Observed failures from
a naive `brand.lower() in label.lower()` over live Sayari results:

    Ring     -> NIPPON PISTON RING COMPANY LIMITED      ("piston ring")
    Reolink  -> REOLINK EZTECH DIGITAL INC  matched ZTE ("e-ZTE-ch")
    Govee    -> GOVE ALUMINIUM FINANCE LIMITED
    Arlo     -> HOMNYUE-ARLO (TAIWAN) CHEMICAL FIBERS
    Sonos    -> ARVATO DIGITAL SERVICES LLC

The ZTE case is the instructive one: a three-letter restriction-list token found
inside an unrelated word would have produced a false FCC Covered List hit on a
consumer camera brand. Short tokens must match on word boundaries.
"""

from __future__ import annotations

import re

# Freight forwarders and marketplaces dominate trade-search results for any brand
# term because they appear on the bill of lading. They are never the manufacturer.
LOGISTICS_TERMS = (
    "schenker", "expeditors", "kuehne", "dhl", "maersk", "amazon", "fedex",
    "logistics", "forwarding", "freight", "shipping line", "cargo",
    "container line", "nippon express", "sinotrans", "cosco", "yusen", "ceva",
    "panalpina", "dsv ", "customs", "deringer", "agility", "geodis",
)

# Bill-of-lading party fields sometimes carry two companies in one string --
# "'Agregator-S Online' LLC через Anker Innovations Ltd" is a Russian reseller
# shipping *via* Anker, not Anker. Accepting these attributes one company's risk
# to another, which is the precise failure mode this pipeline exists to avoid.
COMPOSITE_PARTY_MARKERS = (" через ", " c/o ", " on behalf of ", " по поручению ", " o/b/o ")

_WORD = re.compile(r"[a-z0-9]+")


def normalise(text: str | None) -> str:
    """Lowercase, strip every non-alphanumeric character."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def tokens(text: str | None) -> list[str]:
    return _WORD.findall((text or "").lower())


def is_logistics(label: str | None) -> bool:
    lowered = (label or "").lower()
    return any(term in lowered for term in LOGISTICS_TERMS)


def is_composite_party(label: str | None) -> bool:
    """Two companies in one bill-of-lading party string."""
    lowered = f" {(label or '').lower()} "
    return any(marker in lowered for marker in COMPOSITE_PARTY_MARKERS)


def token_match(needle: str, haystack: str | None) -> bool:
    """Does `needle` appear in `haystack` as a name, not as a substring?

    Short needles (<= 4 chars) must be a whole token: this is what stops "ZTE"
    matching "EZTECH" and "Ring" matching "PISTON RING COMPANY" would still pass
    here on the token rule, so callers also apply per-brand reject rules.

    Longer needles may match a token prefix, so "hikvision" matches
    "HIKVISION DIGITAL TECHNOLOGY" and "tplink" matches "TP-LINK TECHNOLOGIES"
    once punctuation is stripped.
    """
    needle = normalise(needle)
    if not needle:
        return False
    words = tokens(haystack)
    if len(needle) <= 4:
        return needle in words
    if any(word == needle or word.startswith(needle) for word in words):
        return True
    # Brands whose name is split by punctuation ("TP-Link" -> ["tp", "link"])
    # collapse to a single token once normalised.
    return needle in normalise(haystack)


def brand_matches(brand: str, label: str | None) -> bool:
    """Whether an entity label plausibly belongs to this brand."""
    return token_match(brand, label)


# Corporate form suffixes carry no identifying information -- "Inc" matching "Inc"
# is not evidence of anything.
_STOPWORDS = frozenset({
    "inc", "llc", "ltd", "limited", "co", "corp", "corporation", "company",
    "gmbh", "bv", "nv", "sa", "ag", "pte", "pty", "plc", "lp", "llp", "kg",
    "holdings", "holding", "group", "international", "technologies", "technology",
    "the", "and", "of", "de", "sas", "srl", "spa", "oy", "ab", "as",
})


def distinctive_tokens(name: str | None) -> list[str]:
    """Tokens that actually identify a company, ignoring corporate form words."""
    return [t for t in tokens(name) if t not in _STOPWORDS and len(t) > 2]


def name_matches(queried_name: str, label: str | None) -> bool:
    """Whether `label` plausibly answers a search for `queried_name`.

    Used instead of brand matching when a candidate was found via a resolution
    alias, because the right entity frequently does not contain the brand string
    at all:

        Ring  was found as  BOT HOME AUTOMATION, INC.   (its pre-Amazon name)
        Eufy  was found as  ANKER INNOVATIONS LIMITED   (its corporate parent)

    Judging those against the brand token rejects the correct answer. Judging them
    against the name we actually searched for accepts it.
    """
    wanted = distinctive_tokens(queried_name)
    if not wanted:
        return brand_matches(queried_name, label)
    present = set(tokens(label))
    collapsed = normalise(label)

    def seen(token: str) -> bool:
        return (
            token in present
            or any(word.startswith(token) for word in present)
            or token in collapsed
        )

    # The leading distinctive token carries the identity -- it is the company name
    # proper, and the rest is usually descriptive ("Innovation", "Systems"). Requiring
    # it prevents matching on a shared filler word alone; allowing the remainder to be
    # partial lets "Reolink Innovation Limited" match "REOLINK TECHNOLOGY PTE. LTD.",
    # which is the same company under a different corporate form.
    if not seen(wanted[0]):
        return False
    rest = wanted[1:]
    if not rest:
        return True
    return sum(1 for token in rest if seen(token)) >= len(rest) // 2
