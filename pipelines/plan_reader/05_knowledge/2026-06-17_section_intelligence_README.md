# Section Intelligence — empirical corpus analysis (2026-06-17)

Built from `csi_v2.db` (READ-ONLY) over **100 converted plans**, extending Jay's manual boilerplate table with evidence from the `sections`, `gotchas`, and `materials` tables. Every number below comes from an actual query — see `build_section_intelligence.py`.

## TL;DR for the pipeline

- **The bid schedule lives in `bid_schedule`** (proposal form / schedule of prices / bid form). Quantities were extracted from **66/100** plans, sitting ~0.69 of the way through the document (mid/back). The schedule detector should target the `bid_schedule` heading regex, not scan all prose.
- **Gotchas concentrate in a handful of section types.** The top carriers are `special_provisions`, `traffic_staging`, `agreement`, `bid_schedule`, and `contract_front` — together the vast majority of all flagged gotchas. The gotcha pass should be WEIGHTED toward these, not run uniformly over boilerplate.
- **Boilerplate is genuinely low-signal.** `eeo_federal`, `bonds_forms`, `general_conditions`, `title_index` appear in most docs but carry few gotchas and never the bid schedule — these get `rag_weight` ~0.

## Which sections carry gotchas (empirical, by gotcha_count)

| section_type | role | gotchas | docs | go/no-go | pricing | top families |
| --- | --- | --- | --- | --- | --- | --- |
| special_provisions | engineering | 312 | 48 | 205 | 107 | Contract & compliance (112); Site & scope risk (82) |
| traffic_staging | engineering | 173 | 45 | 104 | 69 | Site & scope risk (49); Contract & compliance (45) |
| agreement | keep_high_value | 108 | 42 | 75 | 33 | Contract & compliance (40); Schedule & sequencing (33) |
| bid_schedule | bid_intelligence | 101 | 43 | 63 | 38 | Site & scope risk (43); Contract & compliance (25) |
| contract_front | administrative | 87 | 40 | 43 | 44 | Contract & compliance (44); Schedule & sequencing (16) |
| prevailing_wage | administrative | 50 | 27 | 18 | 32 | Contract & compliance (33); Site & scope risk (10) |
| title_index | administrative | 48 | 17 | 35 | 13 | Schedule & sequencing (18); Site & scope risk (14) |
| prosecution_of_work | engineering | 38 | 11 | 26 | 12 | Contract & compliance (14); Schedule & sequencing (12) |

## Where the bid schedule / quantities live

- `materials` rows (the bid-schedule line items) were extracted from **66/100 plans**, all under the `base_bid` / `alternate_*` buckets = the bid schedule. Normalized page position ≈ **0.69** (mid-to-back of the document).
- Only the **`bid_schedule`** section type has `contains_quantities = Y`. No prose section (special_provisions, agreement, etc.) holds quantities — so a quantity detector should anchor on the bid-schedule heading regex.

## Sections to SKIP (rag_weight ≤ 0.1)

| section_type | jay_category | corpus_freq_% | gotcha_count | rag_weight |
| --- | --- | --- | --- | --- |
| eeo_federal | Federal-Aid / Civil Rights Boilerplate | 91.0 | 16 | 0.02 |
| bonds_forms | Bond / Administrative Forms | 63.0 | 26 | 0.02 |
| title_index | Navigation | 42.0 | 48 | 0.1 |
| general_conditions | Legal / General Conditions | 37.0 | 19 | 0.05 |
| proposal_front | Cover / Front Matter | 3.0 | 0 | 0.05 |

## Recommended RAG weighting map (`rag_weight`)

Use this as a per-section multiplier on retrieval scores. High for the bid-intelligence + engineering core, ~0 for boilerplate. Full values are in `section_taxonomy_proposed.csv`.

| section_type | section_role | rag_weight | corpus_freq_% | gotcha_docs |
| --- | --- | --- | --- | --- |
| bid_schedule | bid_intelligence | 1.0 | 74.0 | 43 |
| special_provisions | engineering | 0.95 | 68.0 | 48 |
| prosecution_of_work | engineering | 0.9 | 19.0 | 11 |
| proposal_front_data | keep_high_value | 0.9 | 57.0 | 3 |
| traffic_staging | engineering | 0.85 | 68.0 | 45 |
| agreement | keep_high_value | 0.85 | 67.0 | 42 |
| general_notes | engineering | 0.85 | 5.0 | 8 |
| specifications | engineering | 0.8 | 66.0 | 13 |
| typical_sections | engineering | 0.75 | 0.0 | 2 |
| geotechnical | engineering | 0.7 | 47.0 | 16 |
| unknown | keep_high_value | 0.6 | 0.0 | 0 |
| prevailing_wage | administrative | 0.4 | 52.0 | 27 |
| contract_front | administrative | 0.2 | 90.0 | 40 |
| title_index | administrative | 0.1 | 42.0 | 17 |
| general_conditions | boilerplate_remove | 0.05 | 37.0 | 10 |
| proposal_front | boilerplate_remove | 0.05 | 3.0 | 0 |
| bonds_forms | boilerplate_remove | 0.02 | 63.0 | 15 |
| eeo_federal | boilerplate_remove | 0.02 | 91.0 | 7 |

## Concrete pipeline recommendations

1. **Schedule detector** — target the `bid_schedule` `heading_regex` (proposal form / schedule of prices / bid form / unit price) instead of scanning every page. It reliably catches the quantity table, which sits mid/back (~0.69 of the doc).
2. **Gotcha pass** — weight retrieval toward the five proven gotcha carriers (`special_provisions`, `traffic_staging`, `agreement`, `bid_schedule`, `contract_front`) plus the engineering specs. Don't spend Claude calls judging `eeo_federal` / `bonds_forms` / `general_conditions` prose — they carry almost no gotchas and never quantities.
3. **Retriever weighting** — multiply chunk scores by `rag_weight`. This demotes boilerplate (~0) without dropping it (a page-level gotcha guard can still rescue a rare flag), and promotes the decision/engineering core.
4. **State-aware framing** — `special_provisions` and `traffic_staging` carry the most gotchas across all three states; MN leans on `general_notes` + `prosecution_of_work` (plan-notes style), while ND/SD push more into `contract_front` and `agreement`. See `state_variants` per row.

## Caveats

- `sections.section_type`/`tier`/`rag_treatment` are still NULL in the DB (Jay's section-spine classification is the pending handoff). `corpus_frequency` here is derived by regex-matching `raw_heading`; the gotcha/decision signal is keyed on the already-normalized `gotchas.section` values.
- Rows with `low_sample_flag = Y` rest on <3 docs — treat as directional.
- Addenda were not processed (per project guardrails).
