"use client";

import { useEffect, useMemo, useState } from "react";
import { Users, Plus, Check, AlertTriangle, Search, Merge, Trash2, Download } from "lucide-react";
import { Glass, Eyebrow, SectionTitle, Chip, NameTypeahead, type Suggestion } from "@/components/kit";
import { cn } from "@/lib/utils";
import { useCompetitorRegistryStore, type RegistryRow } from "@/components/competitor-registry/use-competitor-registry-store";

export default function CompetitorRegistryPage() {
  const store = useCompetitorRegistryStore();
  const [showAdd, setShowAdd] = useState(false);
  const [name, setName] = useState("");
  const [tag, setTag] = useState("");
  const [target, setTarget] = useState("");
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [confirmRemoveRaw, setConfirmRemoveRaw] = useState<string | null>(null);

  useEffect(() => {
    store.fetchRows();
    store.fetchAllRows();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    store.fetchRows(store.search, store.needsReviewOnly);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store.needsReviewOnly]);

  const groups = useMemo(() => {
    const byComp = new Map<string, RegistryRow[]>();
    for (const r of store.rows) {
      const key = r.comp_name?.trim() || "— needs review —";
      if (!byComp.has(key)) byComp.set(key, []);
      byComp.get(key)!.push(r);
    }
    return Array.from(byComp.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [store.rows]);

  const compNameSuggestions = useMemo<Suggestion[]>(() => {
    const names = Array.from(new Set(store.rows.map((r) => r.comp_name).filter(Boolean))) as string[];
    return names.map((n) => ({ key: n, value: n, label: n, searchText: n }));
  }, [store.rows]);

  // Sourced from the full, unfiltered registry (store.allRows), not the sidebar-filtered
  // store.rows — typing "Knife" into the add-competitor field should surface every existing
  // "Knife River ..." variant regardless of what the main list happens to be filtered to.
  const nameSuggestions = useMemo<Suggestion[]>(() => {
    const seen = new Set<string>();
    const out: Suggestion[] = [];
    for (const r of store.allRows) {
      if (seen.has(r.raw_name_variant)) continue;
      seen.add(r.raw_name_variant);
      out.push({
        key: r.raw_name_variant,
        value: r.comp_name || r.raw_name_variant,
        label: (
          <span>
            <span className="font-mono">{r.raw_name_variant}</span>
            {r.comp_name && r.comp_name !== r.raw_name_variant && (
              <span className="ml-1.5 text-muted-foreground">→ {r.comp_name}</span>
            )}
          </span>
        ),
        searchText: `${r.raw_name_variant} ${r.comp_name ?? ""}`,
      });
    }
    return out;
  }, [store.allRows]);

  const submitAdd = async (force = false) => {
    const ok = await store.addCompetitor(name, tag, force);
    if (ok) {
      setName(""); setTag(""); setShowAdd(false);
    }
  };

  const exportCsv = () => {
    const header = ["raw_name_variant", "comp_name", "source", "top_competitors_tag", "suggested_comp"];
    const escape = (v: string | null) => `"${(v ?? "").replace(/"/g, '""')}"`;
    const lines = [
      header.join(","),
      ...store.rows.map((r) =>
        [r.raw_name_variant, r.comp_name, r.source, r.top_competitors_tag, r.suggested_comp].map(escape).join(","),
      ),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `competitor-registry_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto max-w-4xl p-6">
      <Eyebrow>Data · Competitor Registry</Eyebrow>
      <div className="mt-1 flex items-center justify-between">
        <h1 className="font-serif text-2xl tracking-tight">Competitor names</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={exportCsv}
            className="flex items-center gap-1.5 rounded-xl border border-black/10 bg-white/70 px-3.5 py-2 text-[13px] font-medium text-foreground transition-colors hover:bg-white"
          >
            <Download className="h-4 w-4" /> Export CSV
          </button>
          <button
            onClick={() => setShowAdd((s) => !s)}
            className="flex items-center gap-1.5 rounded-xl bg-primary px-3.5 py-2 text-[13px] font-medium text-primary-foreground elev-sm transition-all hover:-translate-y-px hover:elev-md"
          >
            <Plus className="h-4 w-4" /> Add competitor
          </button>
        </div>
      </div>
      <p className="mt-1 max-w-xl text-[13px] text-muted-foreground">
        Select multiple raw names below to consolidate them into one canonical competitor. This
        only renames rows in the registry — it does not change any historical bid results tagged
        with the old name.
      </p>

      {showAdd && (
        <Glass className="mt-4 p-4">
          <SectionTitle>New competitor</SectionTitle>
          <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            <NameTypeahead
              value={name}
              onChange={setName}
              suggestions={nameSuggestions}
              placeholder="Canonical company name"
            />
            <input value={tag} onChange={(e) => setTag(e.target.value)} placeholder="Top Competitors tag (optional)" className={inputCls} />
          </div>
          {store.warning && (
            <div className="mt-3 flex items-start gap-2 rounded-lg bg-[var(--warn)]/10 px-3 py-2.5 text-[12.5px] text-[var(--warn)]">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div className="flex-1">
                <p>{store.warning.message}</p>
                <div className="mt-1.5 flex gap-2">
                  <button onClick={() => submitAdd(true)} className="rounded-md bg-[var(--warn)]/20 px-2 py-1 text-[11px] font-medium">Add anyway</button>
                  <button onClick={() => store.setWarning(null)} className="rounded-md px-2 py-1 text-[11px] font-medium text-muted-foreground">Cancel</button>
                </div>
              </div>
            </div>
          )}
          {store.error && <p className="mt-3 rounded-lg bg-[var(--negative)]/8 px-3 py-2 text-[12px] text-[var(--negative)]">{store.error}</p>}
          <div className="mt-3 flex justify-end gap-2">
            <button onClick={() => setShowAdd(false)} className="rounded-xl px-3 py-2 text-[13px] font-medium text-muted-foreground hover:text-foreground">Cancel</button>
            <button onClick={() => submitAdd(false)} disabled={store.saving} className="flex items-center gap-1.5 rounded-xl bg-primary px-3.5 py-2 text-[13px] font-medium text-primary-foreground disabled:opacity-60">
              <Check className="h-3.5 w-3.5" /> {store.saving ? "Saving…" : "Save"}
            </button>
          </div>
        </Glass>
      )}

      <Glass className="mt-4 p-3">
        <div className="mb-2 flex items-center gap-2">
          <div className="flex flex-1 items-center gap-2 rounded-lg border border-black/10 bg-white/70 px-2.5 py-1.5">
            <Search className="h-3.5 w-3.5 text-muted-foreground" />
            <input
              value={store.search}
              onChange={(e) => store.setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && store.fetchRows(store.search, store.needsReviewOnly)}
              onBlur={() => store.fetchRows(store.search, store.needsReviewOnly)}
              placeholder="Search name…"
              className="w-full bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
            />
          </div>
          <button
            onClick={() => store.setNeedsReviewOnly(!store.needsReviewOnly)}
            className={cn(
              "shrink-0 rounded-lg border px-3 py-1.5 text-[12px] font-medium transition-colors",
              store.needsReviewOnly ? "border-[var(--warn)]/40 bg-[var(--warn)]/10 text-[var(--warn)]" : "border-black/10 text-muted-foreground hover:text-foreground",
            )}
          >
            Needs review
          </button>
        </div>

        <div className="max-h-[500px] space-y-3 overflow-y-auto">
          {store.loading && <p className="px-2 py-4 text-center text-[12px] text-muted-foreground">Loading…</p>}
          {!store.loading && groups.length === 0 && (
            <p className="px-2 py-4 text-center text-[12px] text-muted-foreground">No competitors found.</p>
          )}
          {groups.map(([compName, group]) => (
            <div key={compName} className="rounded-xl border border-black/5 bg-white/30 p-2.5">
              <div className="mb-1.5 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Users className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="text-[13px] font-medium">{compName}</span>
                  {compName === "— needs review —" && <Chip tone="warn">blank comp_name</Chip>}
                </div>
                {compName !== "— needs review —" && (
                  confirmRemove === compName ? (
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => { store.removeCompetitor(compName); setConfirmRemove(null); }}
                        className="rounded-md bg-[var(--negative)]/15 px-2 py-1 text-[11px] font-medium text-[var(--negative)]"
                      >
                        Confirm remove
                      </button>
                      <button
                        onClick={() => setConfirmRemove(null)}
                        className="rounded-md px-2 py-1 text-[11px] font-medium text-muted-foreground hover:text-foreground"
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <button onClick={() => setConfirmRemove(compName)} className="text-muted-foreground transition-colors hover:text-[var(--negative)]">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )
                )}
              </div>
              <div className="space-y-1">
                {group.map((r) => (
                  <div key={r.raw_name_variant} className="flex items-center gap-2 rounded-lg px-2 py-1 text-[12.5px] hover:bg-black/[0.03]">
                    <label className="flex min-w-0 flex-1 items-center gap-2">
                      <input
                        type="checkbox"
                        checked={store.selected.has(r.raw_name_variant)}
                        onChange={() => store.toggleSelected(r.raw_name_variant)}
                        className="h-3.5 w-3.5 shrink-0"
                      />
                      <span className="truncate font-mono text-[12px]">{r.raw_name_variant}</span>
                      {r.suggested_comp && !r.comp_name && (
                        <span className="shrink-0 text-[11px] text-muted-foreground">suggested: {r.suggested_comp}</span>
                      )}
                    </label>
                    {r.source && <span className="shrink-0 text-[10px] text-muted-foreground/70">{r.source}</span>}
                    {confirmRemoveRaw === r.raw_name_variant ? (
                      <div className="flex shrink-0 items-center gap-1">
                        <button
                          onClick={() => { store.removeRawNameVariant(r.raw_name_variant); setConfirmRemoveRaw(null); }}
                          className="rounded-md bg-[var(--negative)]/15 px-1.5 py-0.5 text-[10.5px] font-medium text-[var(--negative)]"
                        >
                          Confirm remove
                        </button>
                        <button
                          onClick={() => setConfirmRemoveRaw(null)}
                          className="rounded-md px-1.5 py-0.5 text-[10.5px] font-medium text-muted-foreground hover:text-foreground"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setConfirmRemoveRaw(r.raw_name_variant)}
                        className="shrink-0 text-muted-foreground transition-colors hover:text-[var(--negative)]"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Glass>

      {store.selected.size > 0 && (
        <div className="fixed inset-x-0 bottom-0 z-10 flex justify-center pb-4">
          <Glass className="flex items-center gap-2 p-2.5 elev-lg">
            <span className="pl-1.5 text-[12.5px] font-medium">{store.selected.size} selected</span>
            <NameTypeahead
              value={target}
              onChange={setTarget}
              suggestions={compNameSuggestions}
              placeholder="Target canonical name…"
              direction="up"
            />
            <button
              onClick={() => store.consolidate(target).then((ok) => ok && setTarget(""))}
              disabled={store.saving}
              className="flex items-center gap-1.5 rounded-xl bg-primary px-3 py-2 text-[12.5px] font-medium text-primary-foreground disabled:opacity-60"
            >
              <Merge className="h-3.5 w-3.5" /> Consolidate
            </button>
            <button onClick={store.clearSelected} className="rounded-xl px-2.5 py-2 text-[12.5px] text-muted-foreground hover:text-foreground">Clear</button>
          </Glass>
        </div>
      )}
      {store.error && (
        <p className="fixed inset-x-0 bottom-20 z-10 mx-auto w-fit rounded-lg bg-[var(--negative)]/10 px-3 py-2 text-[12px] text-[var(--negative)]">
          {store.error}
        </p>
      )}
    </div>
  );
}

const inputCls = "w-full rounded-lg border border-black/10 bg-white/70 px-2.5 py-1.5 text-[13px] outline-none focus:border-primary/50";
