"""2026-08-10_pr102_truncation_probe.py — does #102 make truncation distinguishable from a parse
failure? Runs plan 9786015 at the OLD cap (2048) and reports stop_reason, then shows exactly what
call_json/extract_fields (the shipped code path on #102's branch) do with the same response."""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "h", str(Path(__file__).resolve().parent / "2026-08-10_pr102_stability.py"))
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "01_pipeline"))
import schema                # noqa: E402
import s3_extract            # noqa: E402
import material_tons_merge   # noqa: E402

text = s3_extract.smart_truncate(h.document_text(), s3_extract.MAX_CHARS)
for i in range(2):
    rec, meta = h.one_extraction(text, 2048)
    print(f"run{i} @max_tokens=2048 ->", meta)

prompt = s3_extract.EXTRACTION_PROMPT.format(field_list=schema.extract_prompt_fields(),
                                             archetypes=s3_extract.archetype_choices(),
                                             document_text=text)
data = s3_extract.call_json(prompt, max_tokens=2048)   # what the SHIPPED function reports
print("call_json returned:", repr(data)[:120])
record = {f["name"]: s3_extract._coerce_cell(f, (data or {}).get(f["name"]))
          for f in schema.EXTRACT_FIELDS}
print("merge:", material_tons_merge.merge_material_tons(record))
print("new statuses:", schema.base_unit_status(record), schema.shoulder_unit_status(record),
      schema.mix_unit_status(record))
print("milling_unit_status:", schema.milling_unit_status(record))
print("sample scalars:", {k: schema._cell_value(record, k)
                          for k in ["milling_sy", "grading_quantity", "county", "hot_mix_tons"]})
