# AGENTS.md — conventions for this repo

Project-specific working rules. Read this before touching code.

## What this project is

A Proof of Concept for the Sayari Forward Deployed Engineer exercise
(`FDE_Assessment_Instructions.pdf`), built against **Scenario 1 — Entity Profile
Enrichment with External Source**.

We resolve 25 consumer smart-home device brands to Sayari entity families, then
enrich them with US government restriction lists to answer one question:
**"who is legally barred from buying this?"**

The thesis: *"legal" is not a property of the product — it's a property of the buyer.*
TP-Link is the best-selling router brand in the US **and** on a DoD prohibition list.
Both true, in different legal universes.

## Toolchain

- **Python 3.12, pinned.** The `sayari` SDK declares `>=3.8,<4.0` with classifiers
  only through 3.12. Dev machines may have 3.14 — use `uv python install 3.12`.
- `uv` for Python deps, `npm` for frontend.
- Backend: FastAPI. Frontend: React + TypeScript + Vite, deliberately minimal.

## Git workflow

- `main` stays green. **No direct commits to `main`** after the initial scaffold.
- One branch per build stage: `feat/<stage>`. Merge via PR.
- `.gitignore` must always precede any `git add` that could reach `.env`.

## Sayari SDK gotchas (verified, not guessed)

| Trap | Reality |
|---|---|
| `client.traversal.downstream()` | **Does not exist.** `/v1/downstream` is `client.traversal.ownership()` |
| SDK auto-retries 429s | **It does not.** Internal counter starts at 2, `max_retries` defaults to 0, so `0 > 2` is false → zero retries. We wrap every call ourselves. |
| `sayari.shared_errors.ConnectionError` | **Shadows the builtin.** Import qualified. |
| Traversal `limit=100` | 422. Max is **50**. Traversal does not map 422 to a typed exception — catch `ApiError`, read `.status_code`. |
| `resolution(limit=...)` | Max is **10**. |
| `get_usage(from_=...)` | Trailing underscore; `from` is reserved. |

Rate limits are two-tier and enforced per endpoint:
- **Advanced — 15 req / 10s**: `search`, `traversal`, `ubo`, `downstream`,
  `watchlist`, `shortest_path`, `supply_chain/upstream`
- **Standard — 200 req / min**: everything else

## Correctness rules — non-negotiable

This deliverable's credibility rests on not overstating what the data says. Several
of these correct assumptions that looked reasonable and were wrong.

### Risk semantics

1. **`seed` vs `network`.** `risk_type` says whether a flag is on the entity *itself*
   or derived through the graph. **Never render a network flag as a property of the
   brand.**
2. **`psa_` means two different things.** Check `visibility`, not the prefix:
   - visibility `psa` → entity-identity uncertainty ("possibly the same as")
   - visibility `network` → the traversal was permitted to cross PSA edges, and these
     variants usually **double max depth** (3 → 6). Weaker on two axes, not one.
3. **`sanctioned_adjacent` and `export_controls_adjacent` are DEPRECATED** — still
   returned by the API, no longer shown in Sayari's own UI. **Do not build findings on
   them.** Re-derive from the traversal path and assert against the *target's own seed*
   `sanctioned` / `sanctioned_usa_ofac_sdn`. Check `deprecated` before rendering
   anything — 57 of ~650 factors are.
4. **`meu_list_contractors` is NOT the US Military End User List.** It fires on any
   appearance in government procurement records — *as contractor **or agency*** — in
   China, Russia, or Venezuela (EAR §744.21). Not military-specific.
5. **`_product_blueprint` is *stronger*, not weaker.** The path is observed shipments
   (`receives_from`, depth 4); the blueprint is an HS-code relevance filter over real
   paths. Scored `high` vs `elevated` for the unfiltered variant.
6. **Forced-labor trade factors only cover the last 730 days.** `_origin_direct` =
   tier 1, `_origin_subtier` = tiers 2–3, `_product_blueprint` = tiers 2–4.
7. **`owner_of_*` max depth is 6**, not the "3 hops" its own prose claims.
8. **`cpi_score` is inverted (100 = clean)** and uses the entity's *best* country.
   `cpi_score` / `basel_aml` / `eu_high_risk_third` are country indicators, **not
   allegations about the entity** — group them separately.
9. **Preserve Sayari's hedges.** Its copy says "possibly" and "may have." Never
   compress "may have directly exported" into "exported."
10. **There is no published rubric** for critical/high/elevated/relevant. Say so rather
    than inventing thresholds.

### Evidence

11. **`risk_intelligence` exists only on seed factors.** For a network flag the
    citation lives on the *target* entity — the pipeline must traverse to fetch it.
12. **Date every sanctions claim.** A shipment predating designation is not a
    violation. Use `arrival_date` / `departure_date`; split pre- vs post-designation
    and label both honestly.

### Coverage caveats — these belong in the UI, not buried in the report

13. **Trade data is largely pre-shipment bills of lading** from a freight consortium,
    not confirmed customs clearance. A BoL is an intent-to-ship record.
14. **77 countries, and 25 are sea-only** — including **US (imports only), China,
    Germany, UK, Spain**. Air and land freight from those origins is structurally
    invisible. This bounds every trade-derived claim.
15. **Network risk factors refresh roughly every two weeks.**
16. **`match_strength_v2` is undocumented** — do not interpret it. `score` has no
    documented scale and is **not comparable across queries** — never show it as a
    percentage.
17. **`former` is documented only as "true = no longer exists."** Our observation that
    it is `False` on all 300 SEC-derived rows is *our inference* — label it as such and
    use `last_observed` for recency.

### Framing

18. **A verdict cites a statute or it does not render.** No ethical language anywhere —
    we are not scoring morality, we are reporting legal restriction by buyer class.
19. **No data ≠ no risk.** Ring resolves cleanly with zero flags only because Amazon
    imports on its behalf. The UI must say that, not imply Ring is clean.

## Code style

- Comments earn their place by carrying a constraint, invariant, or footgun the code
  cannot express. No diff narration, no restating self-describing names.
- Prefer the staged pipeline shape: each stage reads the previous stage's artifact and
  writes its own. Stages must be independently re-runnable.
- Keep rejected match candidates in the output. The adjudication *is* the deliverable.
