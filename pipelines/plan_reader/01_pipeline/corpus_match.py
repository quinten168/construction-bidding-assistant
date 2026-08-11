"""
corpus_match.py — ONE matcher for "does this pay-item phrase appear on a real corpus line?".

Runtime-imported module, so it carries no date prefix.

WHY THIS EXISTS: THE FIXED-TOLERANCE MATCHER'S ZERO WAS NOT AN ABSENCE
---------------------------------------------------------------------
`test_material_vocabulary_coverage.py` and `03_evaluation/2026-08-11_alex_conformance_behavior.py`
both need to ask whether a phrase the schema names is a string a real bid schedule actually prints.
Both had their own copy, and the first copy was WRONG in a way that reported a priced bid item as
absent.

pymupdf4llm wraps bid-schedule cells in `**bold**`, `~~strikethrough~~`, `<br>` and table pipes, so
a literal substring search under-reports. The original answer was a tolerant separator — up to 12
non-alphanumeric characters between words. On Stearns 9813645 p77 the corpus prints:

    |~~4 ~~<br><br>|~~2104.504/00080~~<br><br>|~~REMOVE CONCRETE~~<br>DRIVEWAY PAVEMENT<br><br>|...

— **15** characters of markup between CONCRETE and DRIVEWAY. The 12-char matcher returned ZERO hits
for `REMOVE CONCRETE DRIVEWAY PAVEMENT`, and the first pass of the 2026-08-11 conformance inventory
therefore recorded it, and `REMOVE BITUMINOUS DRIVEWAY PAVEMENT`, as `untested-no-plan`. Both are
priced bid items (44 SY and 326 SY). A COVERAGE TEST THAT SILENTLY UNDER-REPORTS IS WORSE THAN NONE:
it converts "we cannot see this" into "this does not exist".

The fix is to strip the converter's markup BEFORE matching rather than to widen the tolerance —
widening only moves the cliff. The residual tolerance stays small (12 chars) so a match still has to
be words-in-order on ONE denoised line, not two unrelated cells of a table.

This is the standing rule in matcher form: **a negative result from a fixed set of checks is not
proof of absence.**
"""
from __future__ import annotations

import re

# Every one of these was observed in this corpus, not guessed: pymupdf4llm's bold/strike/line-break
# markup plus the table pipe and the underscore it emits for empty cells.
_NOISE = re.compile(r"(<br\s*/?>|~~|\*\*|\||_)")

# Residual separator tolerance AFTER denoising — spaces, punctuation, a stray glyph. Deliberately
# small; the markup is meant to be gone by now.
_SEP = r"[^A-Za-z0-9]{0,12}"


def denoise(line: str) -> str:
    """Strip the PDF converter's markdown markup, then collapse whitespace. Match against THIS."""
    return re.sub(r"\s+", " ", _NOISE.sub(" ", line)).strip()


def phrase_pattern(phrase: str) -> re.Pattern:
    """A pattern matching `phrase`'s words, in order, on one DENOISED line, case-insensitively."""
    return re.compile(_SEP.join(re.escape(w) for w in phrase.split()), re.I)


def matches(phrase: str, line: str) -> bool:
    """Does `phrase` appear on `line`, once the converter's markup is out of the way?"""
    return bool(phrase_pattern(phrase).search(denoise(line)))
