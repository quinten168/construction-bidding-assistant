# Road Construction Project Midpoint Finder

Finds the geographic midpoint (latitude/longitude) along a road construction project route, given a state, route number, the begin milepost, and the total gross length from a state DOT plan sheet. The midpoint milepost is calculated as `begin + (total gross length / 2)`.

Supports **Minnesota, North Dakota, South Dakota, Nebraska** (M-value geometry interpolation) and **Montana, Iowa** (ArcGIS LRS API).

---

## How it works

### Step 1 — Read the plan sheet

Open the title sheet of the construction plan. You need four pieces of information:

| Field | Where to find it | Example (MnDOT TH 94) |
|---|---|---|
| State | Header of the plan | `MN` |
| Route number | "Located on TH ___" or similar | `94` |
| Begin milepost | `REF. POINT` under the **first** SP block | `71+00.444` |
| Total gross length | `GROSS LENGTH` row, in miles, under **each** SP block | `3.175`, `7.138`, `2.204` |
| End milepost (optional) | `REF. POINT` under the **last** SP block | `83+00.143` |

The midpoint milepost is `begin + (total gross length / 2)`, where **total gross length** is the sum of the `GROSS LENGTH` (miles) values across every SP block on the plan — pass them all to `--length` as a comma-separated list and the script sums them. The end milepost is optional: if given, it's only printed alongside the implied `end - begin` distance as a cross-check against the gross length, since the two can diverge on projects with station equations (see the `EQUATIONS` block on the plan sheet).

> **Note:** If your project spans multiple State Project (SP) numbers, use the **overall** begin reference post (from the first SP block) and sum the gross length across **all** SP blocks — not just one.

#### State-by-state terminology differences

Not every state calls it a "milepost." Use this table to find the right field on your plan sheet:

| State | Term used | Where to find it | Format |
|---|---|---|---|
| MN | Reference Post (`REF. POINT`) | Under each SP block on the title sheet | Station: `71+00.444` or decimal: `71.004` |
| ND | Reference Post (`RP`) | `Begin/End Project (RP x.x)` labels on the layout map | Decimal only: `4.3`, `34.8` |
| SD | Mileage Reference Marker (`MRM`) | `BEGIN`/`END` labels on the layout map | `MRM 406.32+0.022` — the `+` part is already in miles, so this equals 406.342 miles |
| MT | Reference Post (`RP`) | `RP x.x TO RP x.x` at bottom of layout map | Decimal: `9.9`, `19.7` |
| IA | Mile Post (`MP`) | `±MP xx.xx` at `BEGIN PROJECT` / `END PROJECT` labels on layout map — **state highways only** | Decimal: `18.70`, `21.94` |
| NE | Reference Post (`RP`) | Right margin of title sheet: `REFERENCE POST NO.` | Decimal: `97.59`, `101.79` |

> **ND tip:** The `DESIGN DATA (RP x.xx to RP x.xx)` block at the top left may show a different RP range than the `Begin/End Project` labels on the map. Use the **Begin/End Project** labels — those are the actual project limits.

**North Dakota example** (from a US-52 plan in Burke, Ward & Renville County):
```bash
python road_midpoint.py --state ND --route 52 --begin 4.3 --length 30.5 --end 34.8
```

**South Dakota examples:**

SD MRM format uses `+` to mean additional miles (not hundredths). The script handles this automatically for SD.

```bash
# SD Highway 44, Lincoln County (MRM 406.32+0.022 to 411.84+0.120)
python road_midpoint.py --state SD --route 44 --begin 406.32+0.022 --length 5.520 --end 411.84+0.120

# I-90 near Kadoka (MRM 62.00+0.399 to 71.09+0.111)
python road_midpoint.py --state SD --route 90 --begin 62.00+0.399 --length 9.089 --end 71.09+0.111
```

> **Cross-check tip:** The SD Highway 44 plan sheet includes `Approx. Begin Lat,Long: 43.344480, -96.88578`. After running the script, verify the output latitude is near 43.34 and longitude near -96.88 to confirm the route ID format is correct.

### Step 2 — Run the script

The script calculates the midpoint milepost (`begin + length/2`) and looks up its coordinates using the state DOT's public GIS API.

**Minnesota example (from a TH 94 plan, one SP block):**
```bash
python road_midpoint.py --state MN --route 94 --begin 71+00.444 --length 11.997 --end 83+00.143
```

**Multiple SP blocks — pass each GROSS LENGTH value, comma-separated (from the TH 114 example above):**
```bash
python road_midpoint.py --state MN --route 114 --begin 7+00.272 --length 3.175,7.138,2.204 --end 19+00.949
```

**Decimal milepost format also works:**
```bash
python road_midpoint.py --state MN --route 94 --begin 71.004 --length 11.997 --end 83.001
```

**`--end` is optional** — it's only used to print a cross-check against `--length`, not in the calculation:
```bash
python road_midpoint.py --state MN --route 94 --begin 71.004 --length 11.997
```

**Other states:**
```bash
python road_midpoint.py --state ND --route 52 --begin 4.3   --length 30.5
python road_midpoint.py --state SD --route 90 --begin 200.0 --length 15.5
python road_midpoint.py --state MT --route 2  --begin 110.0 --length 14.3
python road_midpoint.py --state IA --route 35 --begin 88.0  --length 13.5
python road_midpoint.py --state NE --route 80 --begin 300.0 --length 15.0
```

### Step 3 — Read the output

```
Finding midpoint for:
  State          : MN
  Route          : 94
  Begin milepost      : 71.00444
  Total gross length  : 11.9970 mi
  Mid milepost        : 76.9989
  End milepost        : 83.00143  (end - begin = 11.9970 mi)
  Method         : MNDOT_TRAFFIC_DATA M-value interpolation (MN)

Midpoint coordinates:
  Latitude  : 46.123456
  Longitude : -95.654321

  Google Maps: https://maps.google.com/?q=46.123456,-95.654321
```

If `--end` is given and its implied distance (`end - begin`) differs from `--length` by more than 0.05 miles, the script prints a warning to check the plan sheet for station equations.

The Google Maps link opens directly to the midpoint location.

---

## Installation

**Requirements:** Python 3.10+

Install dependencies:
```bash
pip install requests
```

---

## How the API calls work

### MN and ND — M-value geometry interpolation

Both states publish route geometry through ArcGIS feature services where milepost values are embedded directly as M-coordinates (the third value in each polyline vertex). The script:

1. Queries the state's feature service for the route
2. Searches each path in the returned geometry for the two vertices that bracket the target milepost
3. Linearly interpolates between those vertices to get the exact lat/lon

This is the most accurate approach when M-values are available.

| State | Service | Query field |
|---|---|---|
| MN | `dotapp9.dot.state.mn.us/egis12/rest/services/TFA/MNDOT_TRAFFIC_DATA/MapServer/9` | `ROUTE_ID` (e.g. `0300000000000114-I` for TH 114, `0100000000000094-I` for I-94) |
| ND | `gis.dot.nd.gov/ArcGIS/rest/services/external/rcrs_dynamic/MapServer/0` | `HWY_CHAR` (highway number as string) filtered to mainline routes (`RouteId LIKE '%000M'`) |

> **MN note:** The original MnDOT LRS endpoint (`dotapp9.dot.state.mn.us/lrs/...`) is no longer publicly accessible. The script uses the MNDOT_TRAFFIC_DATA layer instead, which has equivalent M-value data.

> **ND note:** ND's `ROUTE_ID` field is an internal integer with no relation to highway numbers. The script queries by `HWY_CHAR` (the highway number as a string) instead.

### MT — ArcGIS LRS API

Montana publishes an **ArcGIS Roads & Highways Linear Referencing Service (LRS)**. The script calls the `measureToGeometry` operation directly with the route ID and milepost. Route IDs are internal codes (e.g. `C000094A`), so the script auto-detects them by querying the Signed Route layer with human-readable codes tried in order: `I-{route}`, `US-{route}`, `MT-{route}`, `S-{route}` (secondary routes).

| State | LRS Endpoint |
|---|---|
| MT | `app.mdt.mt.gov/arcgis/rest/services/ALTIS/ALTIS_API/MapServer/exts/LRSServer` |

> **MT note:** Secondary routes (e.g. S-494 in Fallon County) use the signed route code `S-{route}`. The script tries all four code formats automatically.

### IA — Iowa DOT RAMS LRS

Iowa's RAMS LRS also uses `measureToGeometry`, but route IDs have a complex format: `S{system}{route:04d}{direction}` (e.g., `S001920018E` for US-18 eastbound). The script auto-detects the correct route ID by querying the Reference Posts layer for records near the target milepost, then calls `measureToGeometry` with that ID.

| State | LRS Endpoint | Route ID format |
|---|---|---|
| IA | `gis.iowadot.gov/rams/rest/services/lrs/MapServer/exts/LRSServer` | Auto-detected via Reference Posts layer (system `00191`=Interstate, `00192`=US, `00193`=Iowa) |

> **Iowa note:** Only state-numbered highways (US routes, Iowa routes, Interstates) have milepost values on plan sheets. County and Farm-to-Market road plans use station numbers only and cannot be processed by this script.

### SD — MRM marker interpolation

SD publishes a **DOT_MileageReferenceMarkers** feature service containing point features at each physical mileage reference marker. Each record has a `mrm` field (decimal miles, zero-padded string matching plan sheet MRM values) and direct `mrm_longitude`/`mrm_latitude` coordinates. The script:

1. Queries markers within ±5 MRM of the target milepost for the given highway
2. Finds the two markers that bracket the target MRM
3. Linearly interpolates the coordinates between them

| State | Service | Query field |
|---|---|---|
| SD | `sdgis.sd.gov/dot/rest/services/TIM/DOT_MileageReferenceMarkers/MapServer/0` | `highway` (zero-padded 3-digit, e.g. `'044'` for Hwy 44) |

> **Note:** SD's DOT_Route_System service has M-value offsets on some routes (e.g. Hwy 44 M-values max at ~354 while plan MRM values are 406+). The MRM marker service uses the same MRM values as the plan sheets and does not have this issue.

### NE — M-value geometry interpolation

Nebraska publishes a **HighwaysMajorMinorsLocalRamps_RefPostRoutes** feature service on ArcGIS Online that stores M-values (reference posts) directly in route polyline geometry. The script queries by RouteID (zero-padded 3-digit format, e.g., route 80 → `'080'`, route 680 → `'680'`) and interpolates between bracketing vertices, the same approach used for MN and ND.

| State | Service | Query field |
|---|---|---|
| NE | `services8.arcgis.com/ovrd81pb0zC79CeU/arcgis/rest/services/HighwaysMajorMinorsLocalRamps_RefPostRoutes_7_25/FeatureServer/0` | `RouteID` (zero-padded 3-digit string) |

---

## Known limitations

**County roads, local roads, and multi-road scattered improvement projects may not be supported.** Examples seen in the field:

| State | Unsupported project type | Why |
|---|---|---|
| IA | County/Farm-to-Market roads (e.g. County Road L14 Lyon Co., R77 Hamilton Co., P28 Guthrie Co.) | Uses station numbers (STA), no MP on plan sheet |
| NE | 84th St Trail (Sarpy County) | Local trail, reference post fields blank |
| ND | County road reconstruction projects (e.g. CP-8795) | County roads are not in the ND DOT feature service; plans show station numbers only, no RP values |
| ND | Multi-road projects mixing county and state roads | County road segments cannot be queried; only the state highway portions would be usable |

For these projects, the midpoint coordinate must be determined manually using the plan sheet stationing or a GIS tool.

---

## Troubleshooting

| Error | Likely cause |
|---|---|
| `MN route X not found at milepost Y` | Route number is wrong, or the milepost is outside the route's coverage. Verify the route and REF. POINT values on the title sheet. |
| `ND route X: no mainline geometry found` | Route number doesn't match `HWY_CHAR` in the ND feature service. Check the highway number on the plan. |
| `ND route X: no path found containing RP Y` | The RP value is outside the route's coverage in the feature service. Verify the Begin/End Project RP labels on the layout map. |
| `LRS could not locate route` | Route ID format doesn't match the MT/IA API. |
| `SD route X: no MRM markers found near MRM Y` | Route number not found in SD MRM service, or MRM value is far outside the route's range. Check the highway number and MRM values on the plan. |
| `Connection error / timeout` | The state DOT server may be temporarily down. Try again. |
| Wrong coordinates returned | Double-check you're using the **overall** begin reference post (first SP block), and that `--length` includes the `GROSS LENGTH` from **every** SP block, not just one. For ND, use the **Begin/End Project** map labels, not the Design Data RP range. |
| `WARNING: gross length ... and end - begin ... differ` | Expected on projects with station equations (see the plan sheet's `EQUATIONS` block) — the gross length is generally more reliable than `end - begin` for the calculation. Large mismatches (more than a few tenths of a mile) may indicate a missing SP block in `--length` or a wrong `--begin`/`--end` value. |
