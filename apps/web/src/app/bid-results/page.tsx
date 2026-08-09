"use client";

import { useEffect, useMemo } from "react";
import { Trophy, Plus, Trash2, Search, Check } from "lucide-react";
import { Glass, Eyebrow, SectionTitle, Chip } from "@/components/kit";
import { cn } from "@/lib/utils";
import {
  useBidResultsStore,
  type MissingResultsProject,
} from "@/components/bid-results/use-bid-results-store";
import { BidResultsTable } from "@/components/bid-results/results-table";
import { AccessCompanyPicker } from "@/components/pit-list/access-company-picker";

export default function BidResultsPage() {
  const store = useBidResultsStore();

  useEffect(() => {
    store.fetchProjects();
    store.fetchResults();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Live preview of who the backend will pick as winner (lowest bid_amount) as the user types —
  // mirrors the server's own rule (bid_results_admin.py) so this never promises a winner the save
  // would reject. Blank/unparseable amounts don't count; a tie shows no winner, same as the
  // backend's tie-block.
  const lowestIndex = useMemo(() => {
    const parsed = store.entries.map((e) => (e.bid_amount.trim() ? Number(e.bid_amount) : NaN));
    let best = -1;
    let tied = false;
    parsed.forEach((amount, i) => {
      if (Number.isNaN(amount)) return;
      if (best === -1 || amount < parsed[best]) {
        best = i;
        tied = false;
      } else if (amount === parsed[best]) {
        tied = true;
      }
    });
    return tied ? -1 : best;
  }, [store.entries]);

  return (
    <div className="mx-auto max-w-5xl p-6">
      <Eyebrow>Data · Bid Results</Eyebrow>
      <h1 className="mt-1 font-serif text-2xl tracking-tight">Bid results</h1>
      <p className="mt-1 max-w-xl text-[13px] text-muted-foreground">
        Every recorded bid result, one row per bidder. Click a cell to edit it in place.
      </p>

      <div className="mt-4">
        <BidResultsTable store={store} />
      </div>

      <h2 className="mt-6 font-serif text-lg tracking-tight">Enter results for a new project</h2>
      <p className="mt-1 max-w-xl text-[13px] text-muted-foreground">
        Projects below have no recorded results yet. Enter the bidders and their amounts — the
        winner is set automatically from the lowest bid — this feeds the competitor-intelligence
        model directly.
      </p>

      <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,320px)_1fr]">
        {/* ── Project picker ── */}
        <Glass className="p-3">
          <div className="mb-2 flex items-center gap-2 rounded-lg border border-black/10 bg-white/70 px-2.5 py-1.5">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <input
              value={store.search}
              onChange={(e) => store.setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && store.fetchProjects(store.search)}
              onBlur={() => store.fetchProjects(store.search)}
              placeholder="Search county or project…"
              className="w-full bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div className="max-h-[520px] space-y-1.5 overflow-y-auto">
            {store.loadingProjects && (
              <p className="px-2 py-4 text-center text-[12px] text-muted-foreground">Loading…</p>
            )}
            {!store.loadingProjects && store.projects.length === 0 && (
              <p className="px-2 py-4 text-center text-[12px] text-muted-foreground">
                No projects missing results.
              </p>
            )}
            {store.projects.map((p) => (
              <ProjectRow
                key={p.project_natural_key}
                project={p}
                active={store.selected?.project_natural_key === p.project_natural_key}
                onClick={() => store.selectProject(p)}
              />
            ))}
          </div>
        </Glass>

        {/* ── Entry form ── */}
        <Glass className="p-4">
          {!store.selected ? (
            <div className="grid h-full min-h-[300px] place-items-center text-center text-[13px] text-muted-foreground">
              Pick a project on the left to enter its bid results.
            </div>
          ) : (
            <div>
              <SectionTitle>
                {store.selected.project_name || store.selected.project_natural_key}
              </SectionTitle>
              <p className="mb-3 text-[12px] text-muted-foreground">
                {store.selected.county}, {store.selected.state} · {store.selected.project_natural_key}
              </p>

              <div className="space-y-2">
                {store.entries.map((entry, i) => (
                  <div key={i} className="flex items-center gap-2 rounded-xl border border-black/5 bg-white/40 p-2.5">
                    <div
                      title={i === lowestIndex ? "Currently lowest bid — will be the winner" : undefined}
                      className={cn(
                        "grid h-7 w-7 shrink-0 place-items-center rounded-full border",
                        i === lowestIndex
                          ? "border-[var(--positive)] bg-[var(--positive)] text-white"
                          : "border-black/15 text-transparent",
                      )}
                    >
                      <Trophy className="h-3.5 w-3.5" />
                    </div>
                    <AccessCompanyPicker
                      value={entry.raw_bidder_name}
                      onChange={(v) => store.updateEntry(i, { raw_bidder_name: v })}
                      placeholder="Bidder name"
                      className="min-w-0 flex-1"
                    />
                    <input
                      value={entry.bid_amount}
                      onChange={(e) => store.updateEntry(i, { bid_amount: e.target.value })}
                      placeholder="Bid amount"
                      inputMode="decimal"
                      className="w-32 shrink-0 rounded-lg border border-black/10 bg-white/70 px-2.5 py-1.5 text-right font-mono text-[13px] outline-none focus:border-primary/50"
                    />
                    <button
                      onClick={() => store.removeRow(i)}
                      disabled={store.entries.length <= 1}
                      className="shrink-0 text-muted-foreground transition-colors hover:text-[var(--negative)] disabled:opacity-30"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>

              <div className="mt-2.5 flex items-center justify-between">
                <button
                  onClick={store.addRow}
                  className="flex items-center gap-1.5 text-[12px] font-medium text-primary transition-colors hover:text-primary/80"
                >
                  <Plus className="h-3.5 w-3.5" /> Add bidder ({store.entries.length})
                </button>
                <span className="text-[11px] text-muted-foreground">Winner is set automatically — lowest bid wins</span>
              </div>

              {store.error && (
                <p className="mt-3 rounded-lg bg-[var(--negative)]/8 px-3 py-2 text-[12px] text-[var(--negative)]">
                  {store.error}
                </p>
              )}

              <div className="mt-4 flex justify-end">
                <button
                  onClick={async () => {
                    const ok = await store.submit();
                    if (ok) store.fetchResults();
                  }}
                  disabled={store.submitting}
                  className="flex items-center gap-1.5 rounded-xl bg-primary px-4 py-2.5 text-[13px] font-medium text-primary-foreground elev-sm transition-all hover:-translate-y-px hover:elev-md disabled:opacity-60"
                >
                  <Check className="h-4 w-4" /> {store.submitting ? "Saving…" : "Save results"}
                </button>
              </div>
            </div>
          )}
        </Glass>
      </div>
    </div>
  );
}

function ProjectRow({
  project,
  active,
  onClick,
}: {
  project: MissingResultsProject;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full items-center justify-between gap-2 rounded-xl border px-2.5 py-2 text-left transition-colors",
        active ? "border-primary/40 bg-primary/8" : "border-transparent hover:bg-black/[0.03]",
      )}
    >
      <div className="min-w-0">
        <p className="truncate text-[12.5px] font-medium">{project.project_name || project.project_natural_key}</p>
        <p className="truncate text-[11px] text-muted-foreground">{project.county}, {project.state}</p>
      </div>
      {project.bid_year && <Chip tone="neutral">{project.bid_year}</Chip>}
    </button>
  );
}
