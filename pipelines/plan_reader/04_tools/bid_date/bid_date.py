"""
bid_date.py — extract the BID SUBMISSION DEADLINE (date + time) from bid documents.

Why this exists (2026-08-10): CI capacity is computed per bidding season, the season comes from
the bid date, and when the bid date is missing the system falls back to the construction
completion date, lands in the wrong season, and reports ZERO capacity. So a missing bid date is
not a cosmetic gap.

THREE LAYERS, cheapest first
  1. the standalone advertisement PDF next to the plan set ("<n> AD.pdf", "* AD FOR BIDS.pdf",
     "*Advertisement*.pdf") — a two-page document whose entire purpose is to state the bid date.
  2. the "Advertisement for Bids" page inside the plan set / proposal (e.g. 9786015.pdf p.9 of
     466, City of Fulda CSAH 2: "until Thursday, August 7, 2025, at 11:00am local time").
  3. human entry in the verify step. Not implemented here — layer 3 is the front end's
     (see `apply_verification` in apps/api/backend/report.py). This module's job is that
     layers 1 and 2 populate the field so layer 3 is a correction, not the only source.

STANDING RULE OBEYED: a failure and a legitimate empty answer never share a return value.
`BidDateResult.status` is one of:
    "found"      — bid_date is set. bid_time may still be None (some ads omit it).
    "not_found"  — the document was read successfully and states no bid deadline.
    "error"      — we could not read the document (open failed, no text layer, mojibake font
                   encoding). `error` says which. NEVER conflate this with "not_found".

Run standalone:
    python pipelines/plan_reader/04_tools/bid_date/bid_date.py <pdf-or-directory> [...]
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, asdict, field
from datetime import date as _date
from pathlib import Path
from typing import Iterable, Optional, Sequence

# ─────────────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────────────

STATUS_FOUND = "found"
STATUS_NOT_FOUND = "not_found"
STATUS_ERROR = "error"

LAYER_ADVERTISEMENT_PDF = 1
LAYER_PLAN_SET_PAGE = 2
LAYER_HUMAN = 3


@dataclass
class BidDateResult:
    status: str
    bid_date: Optional[str] = None      # ISO YYYY-MM-DD
    bid_time: Optional[str] = None      # 24h HH:MM
    timezone: Optional[str] = None      # "CT" / "MT" / "local" / None — as written, normalised
    raw: Optional[str] = None           # the sentence it came from, for a human to check
    layer: Optional[int] = None
    source_file: Optional[str] = None
    page: Optional[int] = None          # 1-based
    error: Optional[str] = None         # populated iff status == "error"
    candidates_considered: int = 0

    @property
    def ok(self) -> bool:
        return self.status == STATUS_FOUND

    def as_dict(self) -> dict:
        return asdict(self)

    def deadline_iso(self) -> Optional[str]:
        """'2025-08-07T11:00' when both parts are known, the date alone when only the date is."""
        if not self.bid_date:
            return None
        return f"{self.bid_date}T{self.bid_time}" if self.bid_time else self.bid_date


def _err(msg: str, source: Optional[Path] = None) -> BidDateResult:
    return BidDateResult(status=STATUS_ERROR, error=msg,
                         source_file=(source.name if source else None))


# ─────────────────────────────────────────────────────────────────────────────
# Text normalisation
# ─────────────────────────────────────────────────────────────────────────────

# One corpus AD (8381821 AD.pdf, Renville Co ND) extracts as mojibake — a subset TrueType font
# with no usable cmap. Its text is dense in the 0x0180-0x02FF / Greek-ish range. Reporting that as
# "no bid date on this ad" would be a lie, so we detect it and return status="error".
_LATIN_ISH = re.compile(r"[A-Za-z0-9]")


def looks_like_broken_encoding(text: str) -> bool:
    """True when a PDF produced text but the glyph mapping is broken (mojibake)."""
    stripped = re.sub(r"\s", "", text)
    if len(stripped) < 200:
        return False
    latin = len(_LATIN_ISH.findall(stripped))
    return (latin / len(stripped)) < 0.35


def normalise(text: str) -> str:
    """NBSP/thin-space → space, curly quotes → straight, collapse runs of whitespace.

    The corpus is full of \\xa0 (Swift Co's advertisement is entirely NBSP-separated) — the same
    class of bug that silently bypassed five of the client's rulings in quantity_crosswalk.py.
    """
    text = (text.replace("\xa0", " ").replace(" ", " ").replace(" ", " ")
                .replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"')
                .replace("–", "-").replace("—", "-"))
    return re.sub(r"[ \t]*\n[ \t]*", " ", re.sub(r"[ \t]+", " ", text))


# ─────────────────────────────────────────────────────────────────────────────
# Date / time patterns
# ─────────────────────────────────────────────────────────────────────────────

_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10,
    "november": 11, "nov": 11, "december": 12, "dec": 12,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_ORD = r"(?:st|nd|rd|th)"

# "February 16th, 2023" · "April 25th 2023" · "March 3, 2023"
_RE_MDY = re.compile(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}}){_ORD}?\s*,?\s*(\d{{4}})\b", re.I)
# "the 28th Day of February, 2023" · "22nd day of February, 2023"
_RE_DMY = re.compile(rf"\b(\d{{1,2}}){_ORD}\s+day\s+of\s+({_MONTH_RE})\.?\s*,?\s*(\d{{4}})\b", re.I)
# "2/16/2023" (4-digit year only — a bare "4-12-10" is far more often a statute citation such as
# "N.D.A.C. 4-12-10" than a date, and treating it as a date produced a 2010 bid deadline on a 2023
# plan during the 2026-08-10 measurement).
_RE_NUM = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b")
# "Letting Date: 2/24/2023" — a 2-digit year is only believed directly after an explicit label.
_RE_NUM2 = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2})\b")
_LABEL = re.compile(r"(letting\s+date|bid\s+date|bid\s+opening(?:\s+date)?|bids?\s+close|"
                    r"bids?\s+due|due\s+date|opening\s+date)\s*[:\-]?\s*$", re.I)

# "10:00 AM" · "11:00am" · "9:00 A.M." · "2 p.m." · "1:30 PM" · "11 : 00 AM" (the converter
# sometimes spaces the colon out of a table cell — seen on 8435627)
_RE_TIME = re.compile(r"\b(\d{1,2})(?:\s*:\s*(\d{2}))?\s*([AaPp])\.?\s*[Mm]\.?\b")
_RE_TZ = re.compile(
    r"\b(local\s+time|central\s+(?:standard\s+|daylight\s+)?time|mountain\s+(?:standard\s+|daylight\s+)?time"
    r"|CST|CDT|MST|MDT|CT|MT)\b", re.I)

_TZ_NORM = {"cst": "CT", "cdt": "CT", "ct": "CT", "central": "CT",
            "mst": "MT", "mdt": "MT", "mt": "MT", "mountain": "MT"}


def _norm_tz(raw: str) -> str:
    key = raw.strip().lower()
    if key.startswith("local"):
        return "local"
    if key.startswith("central"):
        return "CT"
    if key.startswith("mountain"):
        return "MT"
    return _TZ_NORM.get(key, raw.strip())


# No trailing \b: "2025-08-07T11:00" from a datetime-local input has no word boundary before "T".
_RE_ISO = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")
# 24-hour clock. Only ever applied to LAYER-3 human input — in a document, "14:30" is far more
# often a station, a sheet reference or a table coordinate than a time.
# (?<![\d:]) rather than \b so the ISO "T" separator in "2025-08-07T11:00" does not block the match.
_RE_TIME24 = re.compile(r"(?<![\d:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])")


def _iter_dates(text: str):
    """Yield (start, end, iso_date) for every parseable calendar date in `text`."""
    for m in _RE_ISO.finditer(text):
        iso = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if iso:
            yield m.start(), m.end(), iso
    for m in _RE_MDY.finditer(text):
        mo, d, y = _MONTHS[m.group(1).lower()], int(m.group(2)), int(m.group(3))
        iso = _safe_date(y, mo, d)
        if iso:
            yield m.start(), m.end(), iso
    for m in _RE_DMY.finditer(text):
        d, mo, y = int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3))
        iso = _safe_date(y, mo, d)
        if iso:
            yield m.start(), m.end(), iso
    for m in _RE_NUM.finditer(text):
        iso = _safe_date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if iso:
            yield m.start(), m.end(), iso
    for m in _RE_NUM2.finditer(text):
        if not _LABEL.search(text[max(0, m.start() - 40):m.start()]):
            continue                                   # bare 2-digit year: almost always a citation
        iso = _safe_date(2000 + int(m.group(3)), int(m.group(1)), int(m.group(2)))
        if iso:
            yield m.start(), m.end(), iso


def _safe_date(y: int, mo: int, d: int) -> Optional[str]:
    if not (1990 <= y <= 2100):
        return None
    try:
        return _date(y, mo, d).isoformat()
    except ValueError:
        return None


def _time_at(text: str, pos: int, radius: int = 160):
    """The clock time nearest `pos` within `radius` chars → ('HH:MM', tz|None) or (None, None)."""
    lo, hi = max(0, pos - radius), min(len(text), pos + radius)
    window = text[lo:hi]
    best = None
    for m in _RE_TIME.finditer(window):
        hour = int(m.group(1))
        if hour == 0 or hour > 12:
            continue
        minute = int(m.group(2) or 0)
        if minute > 59:
            continue
        if m.group(3).lower() == "p" and hour != 12:
            hour += 12
        if m.group(3).lower() == "a" and hour == 12:
            hour = 0
        dist = abs((lo + m.start()) - pos)
        if best is None or dist < best[0]:
            best = (dist, f"{hour:02d}:{minute:02d}", lo + m.end())
    if best is None:
        return None, None
    tz = None
    tzm = _RE_TZ.search(text[best[2]:min(len(text), best[2] + 60)])
    if tzm:
        tz = _norm_tz(tzm.group(1))
    return best[1], tz


# ─────────────────────────────────────────────────────────────────────────────
# Scoring — which date on the page is THE bid deadline
# ─────────────────────────────────────────────────────────────────────────────

# An advertisement page carries several dates. The Fulda page carries the bid deadline AND a
# pre-bid conference ("Monday, July 28, 2025, at 11:00 am"); proposals carry completion dates.
# We score a window around each date rather than taking the first one.
_POSITIVE = [
    # The SDDOT/NDDOT proposal cover states it as two labelled fields rather than a sentence:
    #   "Letting Date: August 20, 2025"  "Bids Close: 9:30 a.m. CST"
    (re.compile(r"\bletting\s+date\b|\bbids?\s+close\b|\bbid\s+opening\s+date\b|\bbids?\s+due\b",
                re.I), 6),
    (re.compile(r"\bbid\s+opening\b", re.I), 5),
    (re.compile(r"\bbids?\s+(?:will\s+be\s+|shall\s+be\s+|are\s+to\s+be\s+)?"
                r"(?:received|accepted|opened|due)\b", re.I), 5),
    (re.compile(r"\breceived\s+(?:by|at|until|and)\b", re.I), 4),
    (re.compile(r"\bsealed\s+bids?\b", re.I), 3),
    (re.compile(r"\buntil\b", re.I), 3),
    (re.compile(r"\bpublicly\s+opened|publically\s+opened|opened\s+and\s+read\b", re.I), 3),
    (re.compile(r"\badvertisement\s+for\s+bids|notice\s+to\s+bidders|invitation\s+(?:for|to)\s+bid",
                re.I), 2),
    (re.compile(r"\blocal\s+time\b", re.I), 1),
]
# Negative anchors: other dates that live in the same neighbourhood and must never win.
_NEGATIVE = [
    (re.compile(r"\bpre-?\s?bid\b", re.I), 8),
    (re.compile(r"\bsubstantial\s+completion|final\s+completion|completion\s+date"
                r"|complete\s+the\s+work\s+by|shall\s+be\s+completed\b", re.I), 8),
    (re.compile(r"\bnotice\s+to\s+proceed\b", re.I), 6),
    (re.compile(r"\baddend(?:um|a)\b", re.I), 4),
    # The deadline for BIDDER QUESTIONS sits a week before the bid date and is worded almost
    # identically ("Written requests must be received by 1:00 p.m., Friday, February 24th, 2023").
    (re.compile(r"\b(?:written\s+)?(?:requests?|questions?|inquir(?:y|ies)|clarifications?|"
                r"substitution\s+requests?)\b", re.I), 6),
    (re.compile(r"\bdeadline\s+for\s+questions|\bamendments?\b", re.I), 3),
    (re.compile(r"\bcopyright|all\s+rights\s+reserved|revised|effective\s+date\b", re.I), 5),
    (re.compile(r"\bexpires?\b|\bbond\s+date\b|\bdated\s+this\b", re.I), 4),
    (re.compile(r"\bpublished\b|\bpublication\b|\bnewspaper\b", re.I), 3),
    # "…as indicated in the plans approved 7/31/2025" — a plan-approval date, not a bid date.
    (re.compile(r"\bapprove[ds]?\b|\bplans\s+approved\b|\bcertifi(?:ed|cation)\b", re.I), 5),
    (re.compile(r"\bN\.?D\.?A\.?C\.?|\bC\.?F\.?R\.?|\bsection\s+\d", re.I), 4),
]

_MIN_SCORE = 4          # below this we do not believe it is a bid deadline
# A candidate with NO stated clock time has to clear a higher bar: every genuine bid deadline in
# the corpus states a time, so a bare date scraping past on one weak anchor is usually a different
# date entirely (a plan-approval or publication date).
_MIN_SCORE_NO_TIME = 8
_WINDOW = 320           # chars either side of the date — where a POSITIVE anchor may sit
# Negatives are scored in a TIGHT window instead. A disqualifying phrase governs the date it is
# attached to ("pre-bid conference … on Monday, July 28", "plans approved 7/31/2025"); the same
# word 200 chars away is unrelated boilerplate. Scoring negatives over the wide window made
# "THE APPROVED DEPARTMENT OF TRANSPORTATION STANDARD SPECIFICATIONS" veto the "Letting Date"
# two lines above it on every MnDOT proposal cover.
_NEG_WINDOW = 110


def score_window(window: str, tight: Optional[str] = None) -> int:
    s = 0
    for rx, w in _POSITIVE:
        if rx.search(window):
            s += w
    for rx, w in _NEGATIVE:
        if rx.search(tight if tight is not None else window):
            s -= w
    return s


@dataclass
class _Candidate:
    score: int
    pos: int
    iso: str
    time: Optional[str]
    tz: Optional[str]
    raw: str


def find_candidates(text: str) -> list:
    """Every bid-deadline candidate in one page/document of text, best first."""
    text = normalise(text)
    out = []
    for s, e, iso in _iter_dates(text):
        window = text[max(0, s - _WINDOW): min(len(text), e + _WINDOW)]
        tight = text[max(0, s - _NEG_WINDOW): min(len(text), e + _NEG_WINDOW)]
        sc = score_window(window, tight)
        if sc < _MIN_SCORE:
            continue
        t, tz = _time_at(text, s)
        if t:
            sc += 2                                   # a stated clock time is corroboration
        elif sc < _MIN_SCORE_NO_TIME:
            continue
        raw = text[max(0, s - 140): min(len(text), e + 90)].strip()
        out.append(_Candidate(sc, s, iso, t, tz, raw))
    out.sort(key=lambda c: (-c.score, c.pos))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Page-level entry points
# ─────────────────────────────────────────────────────────────────────────────

def from_pages(pages: Sequence[tuple], layer: int, source_file: Optional[str] = None) -> BidDateResult:
    """`pages` is an iterable of (page_number, text). Returns the best candidate across pages.

    Raises nothing. A page that is empty is simply a page with no candidates — the caller decides
    whether "no text at all anywhere" is an error (see extract_from_pdf).
    """
    best = None
    considered = 0
    for page_no, text in pages:
        if not text:
            continue
        for c in find_candidates(text):
            considered += 1
            if best is None or c.score > best[0].score:
                best = (c, page_no)
    if best is None:
        return BidDateResult(status=STATUS_NOT_FOUND, layer=layer, source_file=source_file,
                             candidates_considered=considered)
    c, page_no = best
    return BidDateResult(status=STATUS_FOUND, bid_date=c.iso, bid_time=c.time, timezone=c.tz,
                         raw=c.raw, layer=layer, source_file=source_file, page=page_no,
                         candidates_considered=considered)


def parse_free_text(value: str) -> BidDateResult:
    """LAYER 3. Parse a value a human typed into a field already labelled "Bid deadline".

    Deliberately does NOT apply the anchor scoring the document scanners use: the anchors exist to
    pick the bid deadline out of a page full of other dates, and a human typing into a labelled
    box has already done that job. Requiring "bids will be received" of a person who typed
    "August 7, 2025 at 11:00 AM" would reject the correct answer.
    """
    text = normalise(str(value or ""))
    for s, e, iso in _iter_dates(text):
        t, tz = _time_at(text, s, radius=len(text) or 1)
        if t is None:
            # A date picker / datetime-local input sends "2025-08-07 11:00" or "2025-08-07T11:00".
            m = _RE_TIME24.search(text[e:])
            if m:
                t = f"{int(m.group(1)):02d}:{m.group(2)}"
                tzm = _RE_TZ.search(text[e + m.end(): e + m.end() + 40])
                tz = _norm_tz(tzm.group(1)) if tzm else None
        return BidDateResult(status=STATUS_FOUND, bid_date=iso, bid_time=t, timezone=tz,
                             raw=str(value), layer=LAYER_HUMAN, source_file="human")
    return BidDateResult(status=STATUS_ERROR, layer=LAYER_HUMAN, raw=str(value),
                         error="human-entered value could not be parsed as a date")


def read_pdf_pages(pdf: Path, max_pages: Optional[int] = None):
    """(page_number, text) for a PDF, using PyMuPDF. Raises on an unopenable file — callers that
    want an error RESULT rather than an exception should use extract_from_pdf."""
    import fitz
    doc = fitz.open(str(pdf))
    try:
        n = doc.page_count if max_pages is None else min(max_pages, doc.page_count)
        for i in range(n):
            yield i + 1, doc[i].get_text()
    finally:
        doc.close()


def extract_from_pdf(pdf: Path, layer: int = LAYER_ADVERTISEMENT_PDF,
                     max_pages: Optional[int] = None) -> BidDateResult:
    """Read one PDF and return a BidDateResult. Distinguishes four outcomes:
         error  — file will not open / has no text layer / mojibake encoding
         not_found — read fine, no bid deadline stated
         found  — date (and usually time)
    """
    pdf = Path(pdf)
    if not pdf.exists():
        return _err(f"file does not exist: {pdf}", pdf)
    try:
        pages = list(read_pdf_pages(pdf, max_pages))
    except Exception as exc:                                    # noqa: BLE001 — any reader failure
        return _err(f"{type(exc).__name__}: {exc}", pdf)
    joined = "".join(t for _, t in pages)
    if len(joined.strip()) < 40:
        return _err("no extractable text layer (scanned/image-only PDF — needs OCR)", pdf)
    if looks_like_broken_encoding(joined):
        return _err("broken font encoding — text extracts as mojibake (no usable cmap)", pdf)
    return from_pages(pages, layer=layer, source_file=pdf.name)


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — find the standalone advertisement next to a plan set
# ─────────────────────────────────────────────────────────────────────────────

# Corpus naming, verified 2026-08-10 over "the client ELP 2026": "8376434 AD.pdf", "AD.pdf",
# "007-626-019 AD FOR BIDS.pdf", "4130-304_Ad for Bid.pdf", "Advert SAP 061-615-008.pdf",
# "4_1239_Advertisement for Bids (1).pdf", "3 - AD for BID (1).pdf".
_AD_NAME = re.compile(r"(?:^|[\s_\-])ad(?:$|[\s_.\-])|advert", re.I)
# "…a1.pdf" is an ADDENDUM, not an advertisement. Do not let it in on the "ad" substring.
_NOT_AD = re.compile(r"addend|a[0-9]\.pdf$", re.I)


def find_advertisement_pdfs(project_dir: Path) -> list:
    """Every standalone advertisement PDF in a project folder, most-specific name first."""
    project_dir = Path(project_dir)
    if not project_dir.is_dir():
        return []
    hits = [p for p in sorted(project_dir.glob("*.pdf"))
            if _AD_NAME.search(p.name) and not _NOT_AD.search(p.name)]
    # Prefer the small two-page ad over a 250-page document that merely has "ad" in its name.
    hits.sort(key=lambda p: p.stat().st_size)
    return hits


# ─────────────────────────────────────────────────────────────────────────────
# The three-layer orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def extract(plan_pdf: Optional[Path] = None, project_dir: Optional[Path] = None,
            human_value: Optional[str] = None) -> BidDateResult:
    """Layer 1 → layer 2 → layer 3, cheapest first.

    plan_pdf     the plan set / proposal PDF (layer 2)
    project_dir  the folder it sits in; defaults to plan_pdf.parent (layer 1)
    human_value  an already-entered human value; wins outright when present (layer 3)

    Returns a BidDateResult whose `layer` says which one produced it. When every layer comes up
    empty the result is status="not_found" — and if a layer ERRORED on the way, that error is
    carried in `error` so a read failure is never silently reported as an absent date.
    """
    if human_value:
        return parse_free_text(human_value)

    errors = []
    if project_dir is None and plan_pdf is not None:
        project_dir = Path(plan_pdf).parent

    # ── layer 1 ──
    if project_dir is not None:
        for ad in find_advertisement_pdfs(project_dir):
            if plan_pdf is not None and Path(ad).resolve() == Path(plan_pdf).resolve():
                continue
            res = extract_from_pdf(ad, layer=LAYER_ADVERTISEMENT_PDF)
            if res.ok:
                return res
            if res.status == STATUS_ERROR:
                errors.append(f"L1 {ad.name}: {res.error}")

    # ── layer 2 ──
    if plan_pdf is not None:
        res = extract_from_pdf(plan_pdf, layer=LAYER_PLAN_SET_PAGE)
        if res.ok:
            return res
        if res.status == STATUS_ERROR:
            errors.append(f"L2 {Path(plan_pdf).name}: {res.error}")

    # ── nothing found ──
    return BidDateResult(status=STATUS_NOT_FOUND,
                         source_file=(Path(plan_pdf).name if plan_pdf else None),
                         error=("; ".join(errors) or None))


def from_plan_pages(pages: Iterable[tuple], source_file: Optional[str] = None) -> BidDateResult:
    """Layer 2 against ALREADY-CONVERTED pages — what the live PDF-drop path uses, so it costs
    no extra PDF read and no Claude call. `pages` is (page_number, text) pairs."""
    return from_pages(list(pages), layer=LAYER_PLAN_SET_PAGE, source_file=source_file)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: Sequence[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for arg in argv:
        p = Path(arg)
        if p.is_dir():
            res = extract(project_dir=p)
        else:
            res = extract(plan_pdf=p)
        print(f"{p.name}: status={res.status} date={res.bid_date} time={res.bid_time} "
              f"tz={res.timezone} layer={res.layer} src={res.source_file} p.{res.page}")
        if res.error:
            print(f"    error: {res.error}")
        if res.raw:
            print(f"    raw:   {res.raw[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
