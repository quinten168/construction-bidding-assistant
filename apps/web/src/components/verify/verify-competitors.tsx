"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Users, X, ArrowRight, Plus } from "lucide-react";
import { Glass, Eyebrow, Chip, NameTypeahead, type Suggestion } from "@/components/kit";

// Optional 2nd popup, after VerifyExtraction and before finalize: the estimator can type in
// competitors they personally expect to bid, on top of whatever the model already predicted.
// These names render in their OWN section of the report (never blended into the model's
// priority/discovery tiers — they were never run through the model's prediction/ranking scoring,
// since the estimator already asserts they'll bid), but get the exact same win_rate/bid_rate/
// capacity/pit_access figures, computed by the same unified live-SQL retrieval as everyone else.
// Always skippable — nothing downstream depends on this step actually adding anything.
export function VerifyCompetitors({
  onSubmit,
  onSkip,
}: {
  onSubmit: (names: string[]) => void;
  onSkip: () => void;
}) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [draft, setDraft] = useState("");
  const [names, setNames] = useState<string[]>([]);

  // Suggestions from the competitor registry, same endpoint the registry admin page already uses.
  // A plain fetch, not the full admin store/hook — and if it 503s (SUPABASE_TEAM_DB_URL unset, or
  // any other error), NameTypeahead degrades gracefully to a bare text input with no dropdown; the
  // user can still type and add a free-text name.
  useEffect(() => {
    let cancelled = false;
    fetch("/api/ci-data/competitors")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled || !data?.ok) return;
        const seen = new Set<string>();
        const out: Suggestion[] = [];
        for (const row of data.competitors ?? []) {
          const label = (row.comp_name || row.raw_name_variant || "").trim();
          if (!label || seen.has(label)) continue;
          seen.add(label);
          out.push({ key: label, value: label, label, searchText: label });
        }
        setSuggestions(out);
      })
      .catch(() => { /* graceful degrade — free-text entry still works below */ });
    return () => { cancelled = true; };
  }, []);

  const addDraft = () => {
    const v = draft.trim();
    if (!v) return;
    if (!names.some((n) => n.toLowerCase() === v.toLowerCase())) setNames((p) => [...p, v]);
    setDraft("");
  };

  const removeName = (n: string) => setNames((p) => p.filter((x) => x !== n));

  return (
    <div>
      <div className="mb-4">
        <Eyebrow>Step 3 · Optional</Eyebrow>
        <h2 className="mt-1 font-serif text-[22px] tracking-tight">Any competitors you already expect?</h2>
        <p className="mt-1 max-w-lg text-[13px] text-muted-foreground">
          Add anyone you personally expect to bid, on top of the model&rsquo;s predicted list.
          They&rsquo;ll show up in their own section of the report with the same win rate, bid
          rate, capacity, and pit-access figures — nothing to add here if the predicted list looks
          complete.
        </p>
      </div>

      <Glass className="p-4">
        <span className="flex items-center gap-2 text-sm font-medium">
          <Users className="h-4 w-4 text-primary" /> Expected competitors
        </span>
        <div className="mt-2.5 flex flex-wrap items-center gap-2">
          <NameTypeahead
            value={draft}
            onChange={setDraft}
            suggestions={suggestions}
            placeholder="Type a company name…"
          />
          <button
            onClick={addDraft}
            disabled={!draft.trim()}
            className="flex items-center gap-1 rounded-lg bg-primary px-3 py-2 text-[12px] font-medium text-primary-foreground transition-all hover:-translate-y-px disabled:opacity-40"
          >
            <Plus className="h-3.5 w-3.5" /> Add
          </button>
        </div>
        {names.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {names.map((n) => (
              <Chip key={n} tone="primary" className="gap-1.5 py-1">
                {n}
                <button onClick={() => removeName(n)} className="text-primary/70 hover:text-primary" title="Remove">
                  <X className="h-3 w-3" />
                </button>
              </Chip>
            ))}
          </div>
        )}
      </Glass>

      <motion.div layout className="mt-5 flex items-center justify-between gap-3 rounded-2xl border border-black/5 bg-white/40 p-3">
        <span className="text-[13px] text-muted-foreground">
          {names.length === 0
            ? "Nothing added — the predicted list alone is fine."
            : `${names.length} name${names.length === 1 ? "" : "s"} ready to add.`}
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={onSkip}
            className="rounded-xl px-3 py-2.5 text-[13px] font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            Skip — use predicted list only
          </button>
          <button
            onClick={() => onSubmit(names)}
            className="flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2.5 text-[13px] font-medium text-primary-foreground elev-sm transition-all hover:-translate-y-px hover:elev-md"
          >
            {names.length ? "Add & continue" : "Continue"} <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </motion.div>
    </div>
  );
}
