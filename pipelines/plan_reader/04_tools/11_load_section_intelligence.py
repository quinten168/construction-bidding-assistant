#!/usr/bin/env python3
"""
11_load_section_intelligence.py — load the section-intelligence CSV into a DB table so the team can
query it alongside everything else. Idempotent (DROP + recreate). Creates only the NEW
`section_intelligence` table; never touches existing tables. No API.

Run:
    cd 01_Summer_2026
    python3 pipelines/plan_reader/04_tools/11_load_section_intelligence.py
"""
import csv
import sqlite3
from pathlib import Path

MODULE = Path(__file__).resolve().parent.parent
DB = MODULE / "csi_v2.db"
CSV = MODULE / "05_knowledge" / "2026-06-17_section_intelligence.csv"

# columns that should store as numbers (SQLite is dynamically typed, but declare for clarity/clients)
NUM_COLS = {"rag_weight", "corpus_frequency_pct", "docs_with_section", "gotcha_count", "gotcha_docs",
            "go_no_go", "pricing", "avg_gotcha_page", "low_sample_flag"}


def main():
    rows = list(csv.DictReader(open(CSV)))
    cols = list(rows[0].keys())
    coldefs = ", ".join(f'"{c}" {"REAL" if c in NUM_COLS else "TEXT"}' for c in cols)

    conn = sqlite3.connect(DB)
    conn.execute("DROP TABLE IF EXISTS section_intelligence")
    conn.execute(f'CREATE TABLE section_intelligence ({coldefs})')
    placeholders = ", ".join("?" for _ in cols)
    for r in rows:
        vals = []
        for c in cols:
            v = r.get(c, "")
            if c in NUM_COLS and v not in ("", None):
                try:
                    v = float(v)
                except ValueError:
                    pass
            vals.append(v)
        conn.execute(f'INSERT INTO section_intelligence ({", ".join(chr(34)+c+chr(34) for c in cols)}) '
                     f'VALUES ({placeholders})', vals)
    conn.commit()

    n = conn.execute("SELECT COUNT(*) FROM section_intelligence").fetchone()[0]
    print(f"loaded section_intelligence: {n} rows, {len(cols)} columns")
    print("\ntop sections by rag_weight (what the retriever should up-weight):")
    for r in conn.execute("SELECT section_type, rag_weight, gotcha_count, contains_quantities "
                          "FROM section_intelligence ORDER BY rag_weight DESC LIMIT 8"):
        print(f"  {r[0]:22s} rag_weight={r[1]}  gotchas={r[2]}  has_qty={r[3]}")
    conn.close()


if __name__ == "__main__":
    main()
