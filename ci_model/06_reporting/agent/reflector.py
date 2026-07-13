"""
Reflector Agent

Self-critique checkpoint: validates each competitor narrative for correctness,
grounding, and consistency. Up to MAX_REVISIONS attempts per competitor.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_HERE = Path(__file__).resolve().parent.parent
_SYSTEM_PROMPT  = (_HERE / "prompts" / "system_prompt.txt").read_text().strip()
_REFLECT_PROMPT = (_HERE / "prompts" / "reflection_prompt.txt").read_text()

MAX_REVISIONS = 2


def reflect(
    analysis: dict,
    client=None,
    llm_model: str = "claude-sonnet-4-6",
    verbose: bool = False,
) -> dict:
    """
    Quality-check and optionally revise a competitor analysis narrative.

    If no client is provided, skips LLM reflection and returns the analysis unchanged.
    After MAX_REVISIONS failed attempts, flags the entry for human review.

    Args:
        analysis:  output dict from executor.execute_one
        client:    anthropic.Anthropic client (None → skip)
        llm_model: Claude model ID
        verbose:   print reflection results

    Returns:
        analysis dict with (possibly revised) narrative and added reflection metadata.
    """
    if client is None:
        analysis["reflection_passed"] = None
        analysis["reflection_issues"] = []
        return analysis

    for attempt in range(1, MAX_REVISIONS + 1):
        user_msg = _REFLECT_PROMPT.format(
            competitor_name=analysis["display_name"],
            probability=analysis["bid_probability"],
            threat_level=analysis["threat_level"],
            narrative=analysis["narrative"],
        )

        response = client.messages.create(
            model=llm_model,
            max_tokens=512,
            temperature=0.0,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = "\n".join(raw.splitlines()[1:])
            if raw.endswith("```"):
                raw = raw[:-3].strip()

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            if verbose:
                print(f"      [Reflector] JSON parse failed on attempt {attempt}")
            continue

        passed = bool(result.get("passed", False))
        issues = result.get("issues_found", [])
        revised = result.get("revised_narrative", analysis["narrative"]).strip()

        if verbose:
            status = "PASS" if passed else f"FAIL (attempt {attempt})"
            print(f"      [Reflector] {status} — {issues}")

        if passed:
            analysis["narrative"]          = revised
            analysis["reflection_passed"]  = True
            analysis["reflection_issues"]  = []
            return analysis

        # Apply revision and loop
        analysis["narrative"] = revised

    # Exhausted revisions — flag for human review
    analysis["reflection_passed"] = False
    analysis["reflection_issues"] = issues if "issues" in dir() else ["Max revisions reached"]
    if verbose:
        print(f"      [Reflector] Flagged for human review after {MAX_REVISIONS} attempts.")
    return analysis
