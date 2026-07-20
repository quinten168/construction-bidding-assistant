# Material Buckets: definitions to test with CSI (Mark / Alex)

Date: 2026-07-03 (rev 2: buckets + sub-buckets; crushing/stockpile dropped from extraction)
Purpose: we are building a taxonomy that maps every pay-item name in a plan or proposal
(2,400+ distinct names so far, across MN / ND / SD) to the quantity buckets CSI already
tracks. Before we scale it, we want to confirm the buckets match how you think about a job.

Design: two levels. The BUCKET is the number you would say out loud in the Tuesday meeting
("10k tons of mix, 150k tons of aggregate, 180k yards of dirt"). The SUB-BUCKET is what we
actually extract from the bid schedule, so nothing gets blended away and we can still
check our numbers against your 2024/2025 spreadsheet columns.

## The buckets

| Bucket | Sub-bucket (what we extract) | Unit | Example pay-item names by state |
|---|---|---|---|
| **ASPHALT** | Hot mix placed (your MIX TN) | TON | Superpave FAA 42-45, RAP Superpave (ND); Asphalt Concrete (SD); Bituminous, Type SP, spec 2360 (MN); wearing course |
| **AGGREGATE** | Base placed (your BASE TN) | TON | Aggregate Base Course CL 13, Salvaged Base Course (ND), stabilized base |
| | Shoulder / surfacing gravel (your SHLDR TN) | TON | Aggregate surfacing, shoulder gravel, spec 2118 (MN) |
| **GRADING** | Earthwork (your GRADE CY) | CY | Common excavation, embankment, borrow, topsoil, subgrade prep, rock/muck/shale excavation |
| | Removals, converted to CY | TON -> CY | Removal of aggregate base and surfacing, pavement removal (divided by 1.75 Ton/CY) |
| **MILLING** | Milling (your MILL SY) | SY | Cold milling, Milling Asphalt Concrete (SD), reclaim |
| **TOTAL TONS** | Rollup: mix + base + shoulder + removal tons | TON | The "how much has to move by truck" gauge |

Not extracted as quantities (tracked as category flags instead): traffic control, pavement
marking, erosion control, structures (culverts, bridges, pipe), concrete (curb, gutter,
sidewalk, PCC), signing, guardrail, water, testing / lab items, mobilization. Crushing and
stockpile are also not extracted: in your historical data those columns are filled on
under 5% of rows, so we treat them as internal sourcing decisions, not plan quantities.
Also excluded from ASPHALT: tack coat, prime coat, and PG asphalt cement binder lines, so
mix tonnage is never double-counted.

## Questions for CSI

1. **Milling.** Should milling stay its own number, or do you really think of it as part
   of the asphalt work (a "mill and pave" is one job in your head)? Does the milling
   quantity change which crews or equipment you commit, or is it just part of pricing the
   asphalt line?

2. **Concrete.** Curb and gutter, sidewalk, concrete pavement: does CSI ever self-perform
   any of that, or is it always subbed out? If always subbed, we will track it as a flag
   ("this job has concrete work") but never as a CSI quantity.

3. **Aggregate = base + shoulder.** We show one AGGREGATE number that combines base and
   shoulder gravel, with the two visible underneath it. Your spreadsheet tracks them in
   separate columns. Does one combined aggregate number match how you size up a job, or do
   you need base and shoulder called out separately at the top level?

4. **Removals.** On the site visit, Mark said removal tonnage does not count toward the
   base number, but pavement removal "is considered grading work" and gets converted to
   cubic yards for the grading budget.
   a. Can we confirm the rule: removal lines never add to the mix or aggregate numbers,
      and removal work rolls into the grading number?
   b. What conversion do you use from removal tons to cubic yards? (The Dunn County plan
      sheet uses 1.75 Ton/CY for aggregate base. Is that your standard factor?)
   c. We also show removal tonnage inside a TOTAL TONS line (everything that has to move
      by truck). Useful gauge, or noise?

5. **Where you read quantities.** Some projects have a priced bid schedule in the proposal
   AND quantity sheets in the plan set (Basis of Estimate, Estimate of Quantities). When
   the two disagree, which one do you trust? Which one do you actually read first when you
   size up a job?

6. **Who is letting the job.** Does the wording of pay-item names change depending on who
   lets the project (state DOT vs county vs city vs township vs a state-aid SAP/CSAH job),
   or does everyone in a state basically use that state DOT's spec book and item names?

7. **Anything missing.** Are there quantities you wish you tracked on every job that are
   not in this table? (Pipe / utilities footage? Structures counts? Signing?)
