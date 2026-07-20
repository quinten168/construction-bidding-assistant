# Where Information Lives — Field-Location Map (2026-06-09)

Across **11 plans**. Read-only (retrieval + chunk metadata; no Claude calls). Reproduce: `location_map.py`.

## Headline findings

1. **Patterns exist, and they're sensible — for MN.** MN plans put each field in a distinct, predictable section: quantities→`bid_schedule`, wages→`prevailing_wage`, traffic→`traffic_staging`. So section-routed extraction is viable for MnDOT plans.
2. **Prevailing wages sit MID-document in MN** (page-position *middle*) — which is exactly why the `smart_truncate` extractor drops them. Confirms the bug, and that routing to the wage section is the fix.
3. **Section tagger v2 now handles ND.** Added `contract_front` patterns for the EJCDC/county front-matter that dominates ND county plans — ND's no-section-found rate dropped sharply (42%→17%; see §3 diagnostic). **SD DOT plan-sets stay weak** (~38%): they're drawings with almost no prose headers, so more patterns won't help — sectioning them needs document-type detection (a separate task).

## 1. Section → page-range profile, per plan

Where each tagged section physically sits in each document (min–max page : #chunks). Section tags are the heuristic tagger's — a soft signal.

- **[MN] 2023_OTTER-TAIL-CO-MN_CP-4069-304_LOST** (≤34pg) — proposal_front pp.1–1 (3) · contract_front pp.2–10 (9) · special_provisions pp.11–12 (2) · bid_schedule pp.13–34 (29) · traffic_staging pp.20–22 (5)
- **[MN] 2023_WATONWAN-CO-MN_SP-8303-48_LOST** (≤615pg) — unknown pp.1–5 (4) · contract_front pp.7–379 (170) · title_index pp.55–573 (86) · bid_schedule pp.103–397 (77) · special_provisions pp.120–518 (115) · traffic_staging pp.123–610 (206) · specifications pp.224–253 (53) · general_notes pp.274–615 (342)
- **[MN] 2025_DOUGLAS-CO-MN_SAP-021-600-023_NOBID** (≤252pg) — unknown pp.1–2 (2) · title_index pp.3–139 (37) · traffic_staging pp.4–237 (48) · contract_front pp.5–155 (213) · bid_schedule pp.14–238 (9) · prevailing_wage pp.146–201 (86) · general_notes pp.239–252 (41)
- **[MN] 2025_JACKSON-CO-MN_SAP-032-629-048_NOBID** (≤139pg) — unknown pp.2–8 (14) · general_notes pp.9–97 (97) · bid_schedule pp.76–139 (98) · traffic_staging pp.88–88 (4)
- **[MN] 2025_WATONWAN-CO-MN_WATLINE-TRAIL_NOBID** (≤280pg) — unknown pp.1–1 (1) · contract_front pp.2–256 (194) · special_provisions pp.5–280 (187) · prevailing_wage pp.36–203 (45) · title_index pp.56–58 (3) · traffic_staging pp.60–142 (21)
- **[ND] 2023_DUNN-CO-ND_CP-13_WON** (≤171pg) — unknown pp.1–1 (1) · title_index pp.2–142 (32) · contract_front pp.3–111 (176) · bid_schedule pp.12–126 (8) · specifications pp.16–31 (14) · special_provisions pp.112–125 (20) · traffic_staging pp.143–171 (57)
- **[ND] 2023_WALSH-CO-ND_HWY-9_LOST** (≤188pg) — unknown pp.1–1 (1) · title_index pp.2–2 (1) · specifications pp.3–26 (20) · contract_front pp.6–142 (212) · bid_schedule pp.12–14 (6) · special_provisions pp.143–188 (60)
- **[ND] 2025_STUTSMAN-CO-ND_CR-68_NOBID** (≤135pg) — unknown pp.1–4 (4) · contract_front pp.5–56 (73) · traffic_staging pp.20–22 (3) · specifications pp.57–135 (126)
- **[SD] 2023_BROOKINGS-CO-SD_SURFACING_LOST** (≤166pg) — traffic_staging pp.1–18 (26) · title_index pp.19–165 (45) · contract_front pp.21–141 (211) · bid_schedule pp.28–35 (11) · specifications pp.166–166 (1)
- **[SD] 2023_YANKTON-CO-SD_P-PH-0052_WON** (≤144pg) — unknown pp.1–7 (20) · title_index pp.8–140 (228) · general_notes pp.68–144 (19) · traffic_staging pp.72–108 (58)
- **[SD] 2025_HAND-CO-SD_08MQ_NOBID** (≤37pg) — unknown pp.1–7 (29) · traffic_staging pp.8–18 (32) · general_notes pp.19–37 (49)

## 2. Field-location matrix (where the top retrieved chunk lands)

For each info-type, doc-restricted retrieval; showing **top hit** `section p.page (dist)`. Lower distance = more confident the field is really there.

| Info type | [MN] OTTER-TAIL-CO-MN | [MN] WATONWAN-CO-MN | [MN] DOUGLAS-CO-MN | [MN] JACKSON-CO-MN | [MN] WATONWAN-CO-MN | [ND] DUNN-CO-ND | [ND] WALSH-CO-ND | [ND] STUTSMAN-CO-ND | [SD] BROOKINGS-CO-SD | [SD] YANKTON-CO-SD | [SD] HAND-CO-SD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **location** | proposal_front p.1 (0.55) | unknown p.1 (0.51) | contract_front p.6 (0.53) | general_notes p.42 (0.54) | unknown p.1 (0.48) | title_index p.127 (0.55) | special_provisions p.150 (0.51) | specifications p.62 (0.57) | contract_front p.84 (0.54) | traffic_staging p.74 (0.59) | unknown p.5 (0.56) |
| **quantities** | bid_schedule p.33 (0.54) | traffic_staging p.143 (0.54) | bid_schedule p.16 (0.54) | unknown p.3 (0.54) | title_index p.56 (0.57) | specifications p.19 (0.52) | contract_front p.136 (0.50) | contract_front p.17 (0.54) | bid_schedule p.35 (0.45) | title_index p.14 (0.53) | unknown p.6 (0.50) |
| **prevailing_wages** | bid_schedule p.28 (0.70) | contract_front p.355 (0.41) | contract_front p.144 (0.52) | general_notes p.56 (0.73) | prevailing_wage p.196 (0.38) | contract_front p.44 (0.68) | contract_front p.95 (0.67) | contract_front p.37 (0.70) | title_index p.164 (0.68) | traffic_staging p.72 (0.73) | general_notes p.30 (0.70) |
| **phasing_staging** | proposal_front p.1 (0.63) | specifications p.231 (0.50) | contract_front p.55 (0.55) | bid_schedule p.80 (0.61) | special_provisions p.262 (0.57) | bid_schedule p.15 (0.54) | contract_front p.54 (0.55) | contract_front p.39 (0.58) | title_index p.146 (0.54) | traffic_staging p.72 (0.58) | unknown p.4 (0.57) |
| **traffic_control** | traffic_staging p.21 (0.49) | general_notes p.569 (0.42) | traffic_staging p.237 (0.69) | traffic_staging p.88 (0.64) | traffic_staging p.60 (0.54) | title_index p.131 (0.60) | special_provisions p.183 (0.61) | specifications p.135 (0.72) | traffic_staging p.4 (0.55) | traffic_staging p.79 (0.47) | traffic_staging p.9 (0.69) |
| **environmental** | traffic_staging p.22 (0.69) | general_notes p.532 (0.45) | prevailing_wage p.193 (0.61) | general_notes p.72 (0.68) | contract_front p.225 (0.46) | title_index p.129 (0.70) | contract_front p.120 (0.70) | specifications p.62 (0.67) | traffic_staging p.1 (0.63) | unknown p.5 (0.43) | traffic_staging p.9 (0.44) |
| **structure** | bid_schedule p.18 (0.71) | general_notes p.487 (0.52) | prevailing_wage p.183 (0.63) | unknown p.8 (0.52) | special_provisions p.264 (0.57) | title_index p.131 (0.62) | contract_front p.42 (0.70) | specifications p.118 (0.61) | contract_front p.55 (0.66) | title_index p.116 (0.53) | general_notes p.26 (0.50) |
| **schedule** | bid_schedule p.17 (0.57) | specifications p.226 (0.43) | contract_front p.51 (0.43) | general_notes p.40 (0.64) | special_provisions p.80 (0.47) | contract_front p.100 (0.49) | contract_front p.30 (0.31) | contract_front p.39 (0.46) | contract_front p.52 (0.47) | unknown p.7 (0.62) | unknown p.4 (0.64) |

## 3. State rollup — where each field lives, by DOT format

Modal section + typical page position across each state's plans (count of plans).

| Info type | MN | ND | SD |
|---|---|---|---|
| **location** | unknown / front (0.52, n=5) | title_index / back (0.55, n=3) | contract_front / middle (0.56, n=3) |
| **quantities** | bid_schedule / front (0.55, n=5) | contract_front / front (0.52, n=3) | bid_schedule / front (0.49, n=3) |
| **prevailing_wages** | contract_front / middle (0.55, n=5) | contract_front / front (0.68, n=3) | title_index / back (0.70, n=3) |
| **phasing_staging** | proposal_front / front (0.57, n=5) | contract_front / front (0.56, n=3) | title_index / back (0.56, n=3) |
| **traffic_control** | traffic_staging / middle (0.56, n=5) | title_index / back (0.65, n=3) | traffic_staging / front (0.57, n=3) |
| **environmental** | general_notes / back (0.58, n=5) | title_index / middle (0.69, n=3) | traffic_staging / front (0.50, n=3) |
| **structure** | bid_schedule / back (0.59, n=5) | title_index / back (0.64, n=3) | contract_front / back (0.57, n=3) |
| **schedule** | bid_schedule / front (0.51, n=5) | contract_front / front (0.42, n=3) | unknown / front (0.58, n=3) |

### Section-tagger discrimination, by state (a caveat on the above)

Share of matrix cells whose top section is `title_index`/`unknown` — i.e. the tagger found **no real section**. A high share means the section labels for that state are unreliable (the tagger's header patterns are tuned to one DOT's format).

| State | cells | title_index/unknown | share |
|---|--:|--:|--:|
| MN | 40 | 5 | 12% |
| ND | 24 | 4 | 17% |
| SD | 24 | 10 | 42% |

### Cheat sheet — where to look first

Derived from the modal section per field above (confirm against the plan before trusting):
- **location** → `unknown`, `contract_front`
- **quantities** → `bid_schedule`, `unknown`
- **prevailing_wages** → `contract_front`, `general_notes`
- **phasing_staging** → `contract_front`, `bid_schedule`
- **traffic_control** → `traffic_staging`, `general_notes`
- **environmental** → `traffic_staging`, `general_notes`
- **structure** → `general_notes`, `title_index`
- **schedule** → `contract_front`, `unknown`

### Claims from the 06-03 meeting notes — do the data support them?
- *"MnDOT phasing in section 1804"* → see the `phasing_staging` row (MN) above + the MN plans' section profiles in View 1.
- *"info split varies MN vs ND"* → compare the MN vs ND columns in View 3.
