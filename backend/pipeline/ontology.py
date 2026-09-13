"""Sayari's risk-factor ontology -- the glossary every flag is rendered with.

Fetched from /v1/ontology/risk_factors (721 factors). Note the path: /v1/risk_factors
returns 404; the ontology lives under /v1/ontology/*.

This matters for correctness, not just presentation. The ontology is what tells us:

  risk_type   seed   = the flag is on the entity itself
              network = derived by traversing the graph -- NEVER render as a
                        property of the brand
              psa     = derived across a "possibly same as" identity link

  enabled/visible  36 of the 721 are retired at the API level (enabled=false),
                   including the whole plain forced_labor_*_origin_subtier family,
                   superseded by the _product_blueprint variants. A further 2 are
                   marked deprecated in the docs while the API still reports them
                   as enabled -- see DOC_DEPRECATED. Neither may support a finding.

  description      Sayari's own wording, which hedges ("possibly", "may have").
                   We render that verbatim rather than paraphrasing it into
                   something stronger than the data supports.
"""

from __future__ import annotations

import json
from typing import Any

from .client import SayariClient
from .paths import CACHE

# Country-level context indicators. These are NOT allegations about the entity and
# must be grouped separately in any UI. cpi_score is additionally inverted
# (100 = clean) and uses the entity's most favourable country.
CONTEXT_FACTORS = frozenset({"cpi_score", "basel_aml", "eu_high_risk_third"})

# The API and the documentation disagree about these two. Sayari's risk-factor
# reference marks both "deprecated and no longer shows up in the UI", but
# /v1/ontology/risk_factors still returns them with enabled=True. They are also
# the loosest factors in the set -- 1 hop across *any* relationship type -- so
# "ships a container to" scores the same as "is owned by".
#
# We honour the documentation and refuse to build findings on them. The underlying
# facts survive: a sanctioned counterparty is re-derived from the traversal path
# and asserted against that entity's own seed risk instead.
DOC_DEPRECATED = frozenset({"sanctioned_adjacent", "export_controls_adjacent"})

_CACHE_FILE = CACHE / "risk_factors.json"


def load(client: SayariClient | None = None, refresh: bool = False) -> dict[str, dict[str, Any]]:
    """Risk factors keyed by id. Cached; the ontology changes rarely."""
    if _CACHE_FILE.exists() and not refresh:
        return json.loads(_CACHE_FILE.read_text())
    if client is None:
        raise RuntimeError("No cached ontology and no client supplied to fetch it.")

    raw = client.risk_factors()
    if isinstance(raw, dict):
        items = raw.get("data", raw)
        if isinstance(items, dict):
            items = list(items.values())
    else:
        items = raw

    factors: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            item = item.dict() if hasattr(item, "dict") else {}
        record = item
        key = record.get("id")
        if not key:
            continue
        # enabled=False is Sayari retiring a factor outright -- notably the plain
        # forced_labor_*_origin_subtier family, superseded by the _product_blueprint
        # variants that filter the same observed shipment paths for product relevance.
        api_disabled = not (record.get("enabled", True) and record.get("visible", True))
        factors[key] = {
            "id": key,
            "label": record.get("label"),
            "description": record.get("description") or record.get("doc"),
            "level": record.get("level"),
            "risk_type": record.get("risk_type"),
            "categories": record.get("categories") or [],
            "deprecated": api_disabled or key in DOC_DEPRECATED,
            "deprecation_source": (
                "api: enabled=false" if api_disabled
                else "docs: no longer shown in the Sayari UI" if key in DOC_DEPRECATED
                else None
            ),
        }
    CACHE.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(factors, indent=1, ensure_ascii=False))
    return factors


def classify(factor_id: str, factors: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Describe one flag: its wording, severity, derivation, and whether it counts.

    Unknown ids are reported as unknown rather than guessed at -- the ontology is
    the authority, and a factor we cannot describe should not be rendered as if we
    understood it.
    """
    meta = factors.get(factor_id)
    if meta is None:
        return {
            "id": factor_id, "label": factor_id, "description": None, "level": None,
            "risk_type": "unknown", "categories": [], "deprecated": False,
            "deprecation_source": None,
            "is_context": factor_id in CONTEXT_FACTORS, "known": False,
        }
    return {**meta, "is_context": factor_id in CONTEXT_FACTORS, "known": True}


def is_reportable(factor_id: str, factors: dict[str, dict[str, Any]]) -> bool:
    """Whether a flag may be used to support a finding.

    Excludes deprecated factors and country-level context indicators.
    """
    meta = classify(factor_id, factors)
    return not meta["deprecated"] and not meta["is_context"]
