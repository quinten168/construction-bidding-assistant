"""
test_bid_date.py — COVERAGE tests for the bid-date parser.

The point of these is the standing rule on this project: a test that fails when a parser matches
ZERO rows is worth more than thirty passing unit tests. So the load-bearing tests here are:

  * test_every_real_corpus_phrasing_parses — 17 verbatim sentences pulled from real corpus
    advertisements on 2026-08-10 (MN/ND/SD, 2023 and 2025, five different engineering firms'
    boilerplate). If a refactor makes the matcher stop matching, this goes red loudly, and it
    names the phrasing that broke.
  * test_corpus_layer1_hit_rate_does_not_regress — runs layer 1 over the real corpus when it is
    on this machine, and asserts the hit rate stays at or above the measured baseline. Skipped
    (not silently passed) when the corpus is absent.
  * the status tests — prove that "the PDF failed to open" and "no bid date in this document"
    never share a return value.

Run:  pytest pipelines/plan_reader/04_tools/bid_date/test_bid_date.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bid_date  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Real corpus phrasings — (label, text, expected_date, expected_time)
# Every one of these is a verbatim excerpt captured from "CSI ELP 2026" on 2026-08-10.
# ─────────────────────────────────────────────────────────────────────────────
CORPUS_PHRASINGS = [
    ("fulda_plan_set_p9",
     "Bids for the construction of the Project will be received at the Fulda City "
     "Clerk/Treasurer's Office located at 102 3rd Street NE, Fulda, MN, until Thursday, "
     "August 7, 2025, at 11:00am local time. At that time the Bids received will be publicly "
     "opened and read.",
     "2025-08-07", "11:00"),
    ("walsh_co_nd_tz_before_date",
     "Sealed bids will be received by the Walsh County, at the office of the Walsh County "
     "Auditor, 600 Cooper Ave., Grafton, ND 58237, until 10:00 AM CT, February 16th, 2023, at "
     "which time they will be publically opened and read aloud.",
     "2023-02-16", "10:00"),
    ("dunn_co_nd_mt",
     "Sealed bids will be received by the Dunn County Commission, 205 Owens Street, Manning, ND "
     "58642, until 10:00 AM (MT), February 15, 2023, at which time they will publically be "
     "opened and read aloud.",
     "2023-02-15", "10:00"),
    ("blue_earth_co_mn_bidvault",
     "Bids for the contract listed below will be received by the County Board of Commissioners "
     "of Blue Earth County, Minnesota, until 10:00 AM on Wednesday April 26, 2023, through Blue "
     "Earth County's online electronic bid system (bidVAULT).",
     "2023-04-26", "10:00"),
    ("otter_tail_co_mn",
     "Sealed bids will be received until 1:00 PM on Wednesday, April 19, 2023 by the County "
     "Auditor of Otter Tail County for Project No. 4130-304; Wear Courses, Topsoil.",
     "2023-04-19", "13:00"),
    ("meeker_co_mn_periods_in_am",
     "Sealed bids will be received until 9:00 A.M., April 24, 2023 at the Office of the County "
     "Engineer, 422 South Johnson Drive, Litchfield, Mn. 55355 for the overlay, reclaim and "
     "bituminous paving of State Aid Project #'s 047-600-013.",
     "2023-04-24", "09:00"),
    ("pope_co_mn_ordinal",
     "Sealed bids will be received until 10:00 A.M., April 27th, 2023, by the Pope County "
     "Highway Department, on behalf of the County Board of Commissioners.",
     "2023-04-27", "10:00"),
    ("divide_co_nd_local_time_caps",
     "Sealed bids will be received for the construction of 2023 CROSBY CITY-WIDE SIDEWALK "
     "IMPROVEMENTS located in Crosby, North Dakota and received at Interstate Engineering, Inc. "
     "located at 202 13th Street West, Williston, ND 58802-2236 until 3:00 PM LOCAL TIME on "
     "March 3, 2023 and then at said office they will be publicly opened.",
     "2023-03-03", "15:00"),
    ("brookings_co_sd_nth_day_of",
     "Sealed bids will be received by the Brookings County Finance Office, 520 3rd Street Ste. "
     "100 Brookings, South Dakota 57006, until 1:30 PM local time on Tuesday, the 28th Day of "
     "February, 2023 for the above-referenced project.",
     "2023-02-28", "13:30"),
    ("beadle_co_sd_nth_day_lowercase",
     "Sealed bids will be received by the Beadle County Auditor, 450 3rd St. SW, Beadle Co. "
     "Courthouse, Huron, SD 57350, until 11:00 AM local time on Wednesday, the 22nd day of "
     "February, 2023 for the above referenced project.",
     "2023-02-22", "11:00"),
    ("sibley_co_mn_ordinal_month_break",
     "Sealed bids will be received by the Board of County Commissioners of Sibley County, "
     "Minnesota, until 9:30 AM on Thursday, February 16th, 2023, at the Office of Public Works "
     "at 111 8th St., PO Box 897, Gaylord, MN 55334 for the contract listed below.",
     "2023-02-16", "09:30"),
    ("crow_wing_co_mn_bare_until",
     "Sealed bids will be received until 8:00 A.M. on Wednesday, February 22, 2023, at the "
     "office of the Crow Wing County Highway Department, 16589 County Road 142, Brainerd, "
     "Minnesota 56401 for Projects SAP 018-603-024.",
     "2023-02-22", "08:00"),
    ("yellow_medicine_co_mn",
     "Sealed bids will be received until 11:00 A.M. on Tuesday, February 28, 2023 for the "
     "construction of the Granite Falls, Minnesota 2023 STREET & UTILITY IMPROVEMENTS.",
     "2023-02-28", "11:00"),
    ("mclean_co_nd_time_after_date",
     "Bids will be received and accepted via electronic bid (vBid) through QuestCDN until "
     "October 13, 2022 at 2:00 p.m. local time. Bids will be viewed and read via video/phone "
     "conference at 2:30 p.m.",
     "2022-10-13", "14:00"),
    ("pierre_sd_landfill_time_after_date",
     "Bids for the construction of the Project will be received at the City Hall located at "
     "2301 Patron Parkway until February 6th, 2025 at 4:00pm local time. At that time the Bids "
     "received will be publicly opened and read.",
     "2025-02-06", "16:00"),
    ("swift_co_mn_nbsp_bid_opening_at",
     "Sealed\xa0bids\xa0will\xa0be\xa0received\xa0until:\xa0\xa0BID\xa0OPENING\xa0@\xa010:00\xa0AM"
     "\xa0Tuesday\xa0April\xa025th\xa02023\xa0\xa0by\xa0the\xa0County\xa0Engineer\xa0on\xa0behalf"
     "\xa0of\xa0the\xa0Swift\xa0County\xa0Board.",
     "2023-04-25", "10:00"),
    # MnDOT/SDDOT proposal covers state it as two labelled fields, not a sentence. Both plans in
    # _md_cache that used this form returned NOTHING until it was added — the whole-state form.
    ("mndot_proposal_cover_letting_date",
     "###### **Proposal** **Letting Date: August 20, 2025** **Bids Close: 9:30 a.m. CST** "
     "**NOTICE TO BIDDERS: ALL BIDS MUST BE SUBMITTED ELECTRONICALLY VIA BID EXPRESS.** TO "
     "FURNISH AND DELIVER ALL MATERIALS AND TO PERFORM ALL WORK IN ACCORDANCE WITH THE CONTRACT, "
     "THE PLANS AND THE APPROVED DEPARTMENT OF TRANSPORTATION STANDARD SPECIFICATIONS FOR "
     "CONSTRUCTION, 2020 EDITION.",
     "2025-08-20", "09:30"),
    ("mndot_proposal_cover_numeric_letting_date",
     "**Proposal** **Letting Date: 2/24/2023** **Bids Close: 9:30 a.m. CST** **NOTICE TO "
     "BIDDERS: ALL BIDS MUST BE SUBMITTED ELECTRONICALLY VIA BID EXPRESS.**",
     "2023-02-24", "09:30"),
    ("nddot_bidx_time_before_date",
     "**BID OPENING:** The bidder's proposal will be accepted via the Bid Express on-line "
     "bidding exchange at www.bidx.com until **09:30AM Central Time on August 15, 2025**.",
     "2025-08-15", "09:30"),
    ("spaced_colon_from_table_cell",
     "**Bid Proposal** AIP NO. 3-38-0033-020-2022 **Bid Opening:** **April 27, 2023** "
     "**11 : 00 AM CT (Bid Due by 10:00 AM CT)**",
     "2023-04-27", "11:00"),
    ("todd_co_mn_2025",
     "Sealed bids will be received until 10:00 A.M., March 11th, 2025 by the Todd County Public "
     "Works Director/Engineer and County Auditor/Treasurer at 44 Riverside Drive, Long Prairie, "
     "Minnesota 56347 for the following construction projects.",
     "2025-03-11", "10:00"),
]


@pytest.mark.parametrize("label,text,exp_date,exp_time",
                         CORPUS_PHRASINGS, ids=[p[0] for p in CORPUS_PHRASINGS])
def test_every_real_corpus_phrasing_parses(label, text, exp_date, exp_time):
    """COVERAGE: every phrasing seen in the real corpus must still parse. Zero matches is a
    failure, not an empty answer."""
    res = bid_date.from_pages([(1, text)], layer=bid_date.LAYER_ADVERTISEMENT_PDF)
    assert res.status == bid_date.STATUS_FOUND, f"{label}: matched nothing"
    assert res.bid_date == exp_date, f"{label}: wrong date"
    assert res.bid_time == exp_time, f"{label}: wrong time"


def test_coverage_floor_all_phrasings():
    """A single assertion that goes red the moment the matcher stops matching the corpus at all —
    the "fails when the parser matches zero rows" test."""
    hits = sum(1 for _, text, _, _ in CORPUS_PHRASINGS
               if bid_date.from_pages([(1, text)], layer=1).ok)
    assert hits == len(CORPUS_PHRASINGS), (
        f"bid-date matcher covers {hits}/{len(CORPUS_PHRASINGS)} real corpus phrasings")


# ─────────────────────────────────────────────────────────────────────────────
# The bid deadline must beat the other dates that sit beside it
# ─────────────────────────────────────────────────────────────────────────────

# Verbatim page 9 of 466 of 9786015.pdf (City of Fulda CSAH 2) — the page the earlier note
# claimed did not exist in the plan set. It states the bid deadline AND a pre-bid conference.
FULDA_P9 = (
    "**ADVERTISEMENT FOR BIDS** **CITY OF FULDA (Owner)** **FULDA, MINNESOTA** **CSAH 2 "
    "INFRASTRUCTURE IMPROVEMENTS** **General Notice** **City of Fulda** (Owner) is requesting "
    "Bids for the construction of the following Project: **CSAH 2 Infrastructure Improvements** "
    "**254021** Bids for the construction of the Project will be received at the **Fulda City "
    "Clerk/Treasurer's Office** located at **102 3** **[rd]** **Street NE, Fulda, MN**, until "
    "**Thursday, August 7, 2025,** at **11:00am** local time. The opening and reading of the "
    "Bids may be modified subject to COVID-19 preventative measures. At that time the Bids "
    "received will be publicly opened and read. The Project includes the following Work: **748 "
    "LF open cut watermain, 287 LF trenchless watermain, 1,994 LF open cut sanitary sewer, 134** "
    "**LF trenchless sanitary sewer, 7,071 SY bituminous paving, 1,046 LF curb and gutter, and "
    "2,510 SF** **concrete sidewalk.** Bids are requested for the following Contract: **CSAH 2** "
    "**Infrastructure Improvements** **Obtaining the Bidding Documents** The Issuing Office for "
    "the Bidding Documents is: **Bollig Engineering** **5031 E. Rosa Parks Place, Ste 102** "
    "**Sioux Falls, SD 57110** Prospective Bidders may obtain or examine the Bidding Documents "
    "at the Issuing Office on Monday through Friday between the hours of **8:00 a.m. and 5:00 "
    "p.m.** and may obtain copies of the Bidding Documents from the Issuing Office as described "
    "below. Partial sets of Bidding Documents will not be available from the Issuing Office. "
    "Bidding Documents may also be examined at the Sioux Falls Builders Exchange, 1418 N C Ave, "
    "Sioux Falls, SD 57104 or may be purchased online at www.bolligengineering.com under the "
    "bidding tab through QuestCDN for **$40**. Printed copies of the Bidding Documents may be "
    "obtained from the Issuing Office by paying a deposit of **$100** for each set. Bidders who "
    "return full sets of the Bidding Documents in good condition within 10 days after receipt of "
    "Bids will receive a refund of **$60.00**. Make deposit checks payable to Bollig "
    "Engineering. **Pre-bid Conference** A pre-bid conference for the Project will be held on "
    "**Monday, July 28, 2025, at 11:00 am** at the office of the Fulda City Clerk/Treasurer, "
    "102 3 [rd] Street NE, Fulda, MN. Attendance at the pre-bid conference is encouraged but "
    "not required. **EJCDC C-111, Advertisement for Bids for Construction Contract.** "
    "**Copyright 2018 National Society of Professional Engineers.** **Page 1 of 2**")


def test_prebid_conference_date_does_not_win():
    """Fulda p.9 states BOTH. The pre-bid conference must never be returned as the bid deadline."""
    res = bid_date.from_pages([(9, FULDA_P9)], layer=bid_date.LAYER_PLAN_SET_PAGE)
    assert res.status == bid_date.STATUS_FOUND
    assert (res.bid_date, res.bid_time, res.timezone) == ("2025-08-07", "11:00", "local")
    assert res.page == 9


def test_completion_date_does_not_win():
    text = ("Sealed bids will be received until 10:00 AM on Wednesday April 26, 2023. "
            "The Work shall be substantially completed by October 15, 2023 and finally "
            "completed by November 1, 2023.")
    res = bid_date.from_pages([(1, text)], layer=1)
    assert res.bid_date == "2023-04-26"


def test_bidder_question_deadline_does_not_win():
    """8395536 (Divide Co ND): the plan set states only the deadline for WRITTEN QUESTIONS, worded
    almost identically to a bid deadline. Returning it would put the project a week early into the
    wrong season — exactly the failure this task exists to fix."""
    text = ("Questions regarding the 2023 Crosby City-Wide Sidewalk Improvements Project (IE "
            "Project No. WC22-00-131). Written requests must be received by 1:00 p.m., Friday, "
            "February 24th, 2023 to allow issuance of any necessary amendments.")
    res = bid_date.from_pages([(23, text)], layer=bid_date.LAYER_PLAN_SET_PAGE)
    assert res.status == bid_date.STATUS_NOT_FOUND


def test_copyright_year_is_not_a_bid_date():
    text = ("EJCDC C-111, Advertisement for Bids for Construction Contract. Copyright 2018 "
            "National Society of Professional Engineers. All rights reserved. Page 1 of 2. "
            "Revised January 1, 2018.")
    res = bid_date.from_pages([(1, text)], layer=1)
    assert res.status == bid_date.STATUS_NOT_FOUND


# ─────────────────────────────────────────────────────────────────────────────
# Failure and empty answer must not share a return value
# ─────────────────────────────────────────────────────────────────────────────

def test_missing_file_is_error_not_not_found(tmp_path):
    res = bid_date.extract_from_pdf(tmp_path / "nope.pdf")
    assert res.status == bid_date.STATUS_ERROR
    assert res.error and res.bid_date is None


def test_unreadable_pdf_is_error_not_not_found(tmp_path):
    bad = tmp_path / "broken.pdf"
    bad.write_bytes(b"not a pdf at all")
    res = bid_date.extract_from_pdf(bad)
    assert res.status == bid_date.STATUS_ERROR
    assert res.status != bid_date.STATUS_NOT_FOUND


def test_document_with_no_bid_date_is_not_found_not_error():
    text = ("Per Delapre Twp there is no bid form or bidding documents for this project. "
            "LJ 2/27. " * 20)
    res = bid_date.from_pages([(1, text)], layer=1)
    assert res.status == bid_date.STATUS_NOT_FOUND
    assert res.error is None


def test_mojibake_is_detected_as_error():
    """8381821 AD.pdf (Renville Co ND) extracts as mojibake — a subset font with no cmap.
    Reporting that as 'this advertisement has no bid date' would be a lie."""
    mojibake = ("sZd/^DEd&KZ/^ EKd//^,Zz'/sEd,d ƚŚĞŽŵŵŝƐƐŝŽŶĞƌƐ ŽĨ ƚŚĞ ŽƵŶƚǇ ŽĨ ZĞŶǀŝůůĞ "
                "ϭϬ͗ϬϬ͘D͘^dŽŶ&ĞďƌƵĂƌǇϮϭ͕ϮϬϮϯ ǁŝůůƌĞĐĞŝǀĞƐĞĂůĞĚďŝĚƐ " * 6)
    assert bid_date.looks_like_broken_encoding(mojibake)
    assert not bid_date.looks_like_broken_encoding(CORPUS_PHRASINGS[0][1] * 4)


def test_unparseable_human_entry_is_error():
    res = bid_date.extract(human_value="whenever, probably")
    assert res.status == bid_date.STATUS_ERROR
    assert res.layer == bid_date.LAYER_HUMAN


# Layer 3 is Wenyu's verify popup. What it can send is unknown at time of writing, so the parser
# accepts every plausible shape a date field or a free-text box produces — and, unlike layers 1
# and 2, applies NO anchor scoring: a human typing into a box labelled "Bid deadline" has already
# picked the right date out of the document.
@pytest.mark.parametrize("typed,exp_date,exp_time,exp_tz", [
    ("Bids due August 7, 2025 at 11:00 AM local time", "2025-08-07", "11:00", "local"),
    ("Thursday, August 7, 2025 at 11:00am local time", "2025-08-07", "11:00", "local"),
    ("August 7, 2025", "2025-08-07", None, None),
    ("2025-08-07", "2025-08-07", None, None),
    ("2025-08-07 11:00", "2025-08-07", "11:00", None),          # <input type=datetime-local>
    ("2025-08-07T11:00 CT", "2025-08-07", "11:00", "CT"),
    ("8/7/2025 11:00 AM CT", "2025-08-07", "11:00", "CT"),
])
def test_human_entry_shapes(typed, exp_date, exp_time, exp_tz):
    res = bid_date.extract(human_value=typed)
    assert res.status == bid_date.STATUS_FOUND, typed
    assert (res.bid_date, res.bid_time, res.timezone, res.layer) == (exp_date, exp_time, exp_tz, 3)


# ─────────────────────────────────────────────────────────────────────────────
# Advertisement-file discovery (layer 1)
# ─────────────────────────────────────────────────────────────────────────────

def test_addendum_is_not_mistaken_for_an_advertisement(tmp_path):
    for name in ("8376434 AD.pdf", "8376434a1.pdf", "8376434.pdf", "8376434 QUANITIES.pdf"):
        (tmp_path / name).write_bytes(b"x")
    names = [p.name for p in bid_date.find_advertisement_pdfs(tmp_path)]
    assert names == ["8376434 AD.pdf"]


@pytest.mark.parametrize("name", [
    "8376434 AD.pdf", "AD.pdf", "007-626-019 AD FOR BIDS.pdf", "4130-304_Ad for Bid.pdf",
    "Advert SAP 061-615-008.pdf", "4_1239_Advertisement for Bids (1).pdf",
    "3 - AD for BID (1).pdf", "076-606-048 ADVERTISEMENT.pdf",
])
def test_real_corpus_ad_filenames_are_recognised(tmp_path, name):
    (tmp_path / name).write_bytes(b"x")
    assert [p.name for p in bid_date.find_advertisement_pdfs(tmp_path)] == [name]


def test_deadline_iso_roundtrip():
    res = bid_date.BidDateResult(status="found", bid_date="2025-08-07", bid_time="11:00")
    assert res.deadline_iso() == "2025-08-07T11:00"
    assert bid_date.BidDateResult(status="found", bid_date="2025-08-07").deadline_iso() == "2025-08-07"
    assert bid_date.BidDateResult(status="not_found").deadline_iso() is None


# ─────────────────────────────────────────────────────────────────────────────
# Corpus regression floor — skipped, never silently passed, when the corpus is absent
# ─────────────────────────────────────────────────────────────────────────────

CORPUS_ROOTS = [
    Path("/Users/t/Library/Mobile Documents/com~apple~CloudDocs/00 MSBA + Coding/"
         "00_summer 2026/00_CSI_ELP/CSI ELP 2026"),
    Path("/Users/t/Library/CloudStorage/Box-Box/CSI ELP 2026"),
]

# Measured 2026-08-10: 22 advertisement PDFs, 19 found, 2 genuinely-no-bid-date scanned notes,
# 1 mojibake. Floor is set at the measured value — a drop means a regression.
BASELINE_ADS = 22
BASELINE_FOUND = 19


def _corpus_root():
    for r in CORPUS_ROOTS:
        if r.is_dir():
            return r
    return None


@pytest.mark.skipif(_corpus_root() is None, reason="CSI ELP 2026 corpus not on this machine")
def test_corpus_layer1_hit_rate_does_not_regress():
    root = _corpus_root()
    ads = [p for p in root.rglob("*.pdf")
           if bid_date._AD_NAME.search(p.name) and not bid_date._NOT_AD.search(p.name)]
    assert len(ads) >= BASELINE_ADS, f"only {len(ads)} advertisement PDFs discovered"
    results = [bid_date.extract_from_pdf(p) for p in ads]
    found = sum(1 for r in results if r.ok)
    assert found >= BASELINE_FOUND, (
        f"layer-1 hit rate regressed: {found}/{len(ads)} (baseline {BASELINE_FOUND}/{BASELINE_ADS})")
    # every hit must carry a clock time — CI needs date AND time
    assert all(r.bid_time for r in results if r.ok), "a layer-1 hit came back without a time"


# ── layer 2 against the local converted-markdown cache — no corpus, no Box, no re-conversion ──

MD_CACHE = Path(__file__).resolve().parents[2] / "00_input" / "_md_cache"
# Measured 2026-08-10: 17 converted plans, 16 found. The 1 not_found (8395536) genuinely does not
# state a bid deadline anywhere in the plan set — its standalone AD does, which is why layer 1
# exists. Raising this floor is good; a drop is a regression.
BASELINE_MD_PLANS = 17
BASELINE_MD_FOUND = 16


@pytest.mark.skipif(not MD_CACHE.is_dir(), reason="no converted-markdown cache on this machine")
def test_layer2_coverage_over_converted_plans_does_not_regress():
    import json
    hashes = sorted({p.name.split(".")[0] for p in MD_CACHE.glob("*.json")})
    assert len(hashes) >= BASELINE_MD_PLANS, f"only {len(hashes)} converted plans in the cache"
    found = 0
    for h in hashes:
        f = MD_CACHE / f"{h}.hybrid.json"
        if not f.exists():
            f = MD_CACHE / f"{h}.json"
        pages = json.loads(f.read_text())
        res = bid_date.from_plan_pages([(p.get("page"), p.get("text", "")) for p in pages],
                                       source_file=h)
        assert res.status != bid_date.STATUS_ERROR, f"{h}: {res.error}"
        found += res.ok
    assert found >= BASELINE_MD_FOUND, (
        f"layer-2 coverage regressed: {found}/{len(hashes)} "
        f"(baseline {BASELINE_MD_FOUND}/{BASELINE_MD_PLANS})")
