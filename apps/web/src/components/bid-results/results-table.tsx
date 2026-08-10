"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, ChevronsUpDown, ListFilter, Search, Trophy } from "lucide-react";
import { Glass } from "@/components/kit";
import { cn } from "@/lib/utils";
import type { BidResultRow, useBidResultsStore } from "./use-bid-results-store";

const PAGE_SIZE = 100;
const BLANK = "(Blanks)";

const dateStr = (d: string | null) =>
  d
    ? new Date(`${d}T00:00:00`).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" })
    : "—";

// ── Generic sort/filter helpers (kept local to this file by design) ─────────

type SortDir = "asc" | "desc";
type SortKey = "bid_date" | "project_name" | "county_state" | "raw_bidder_name" | "bid_amount" | "bid_rank" | "did_win";
type SortState = { key: SortKey | null; dir: SortDir };
type NumRange = { min: string; max: string };
type DateRange = { from: string; to: string };
type WinnerOption = "Winner" | "Not winner";

const bucket = (v: string | null) => (v && v.trim() ? v : BLANK);

function uniqueValues(rows: BidResultRow[], getValue: (row: BidResultRow) => string | null): string[] {
  const set = new Set<string>();
  let hasBlank = false;
  for (const row of rows) {
    const v = getValue(row);
    if (v && v.trim()) set.add(v);
    else hasBlank = true;
  }
  const sorted = Array.from(set).sort((a, b) => a.localeCompare(b));
  return hasBlank ? [...sorted, BLANK] : sorted;
}

function makeComparator<T>(getValue: (row: T) => string | number | null, dir: SortDir) {
  return (a: T, b: T) => {
    const va = getValue(a);
    const vb = getValue(b);
    if (va == null && vb == null) return 0;
    if (va == null) return 1; // nulls always last, regardless of direction
    if (vb == null) return -1;
    const base = typeof va === "number" && typeof vb === "number" ? va - vb : String(va).localeCompare(String(vb));
    return dir === "asc" ? base : -base;
  };
}

function inRange(value: number | null, range: NumRange): boolean {
  if (!range.min && !range.max) return true;
  if (value == null) return false;
  const min = range.min ? Number(range.min) : -Infinity;
  const max = range.max ? Number(range.max) : Infinity;
  return value >= min && value <= max;
}

function inDateRange(value: string | null, range: DateRange): boolean {
  if (!range.from && !range.to) return true;
  if (value == null) return false;
  if (range.from && value < range.from) return false;
  if (range.to && value > range.to) return false;
  return true;
}

const SORTERS: Record<SortKey, (dir: SortDir) => (a: BidResultRow, b: BidResultRow) => number> = {
  bid_date: (dir) => makeComparator((r: BidResultRow) => r.bid_date, dir),
  project_name: (dir) => makeComparator((r: BidResultRow) => r.project_name, dir),
  county_state: (dir) => (a, b) => {
    const c = makeComparator((r: BidResultRow) => r.county, dir)(a, b);
    return c !== 0 ? c : makeComparator((r: BidResultRow) => r.state, dir)(a, b);
  },
  raw_bidder_name: (dir) => makeComparator((r: BidResultRow) => r.raw_bidder_name, dir),
  bid_amount: (dir) => makeComparator((r: BidResultRow) => r.bid_amount, dir),
  bid_rank: (dir) => makeComparator((r: BidResultRow) => r.bid_rank, dir),
  did_win: (dir) => makeComparator((r: BidResultRow) => (r.did_win ? 1 : 0), dir),
};

type Store = ReturnType<typeof useBidResultsStore>;

export function BidResultsTable({ store }: { store: Store }) {
  const [page, setPage] = useState(0);
  // Default to grouping by project (still a normal, clickable/cyclable column sort underneath —
  // click "Project" again to reverse, or another column header to sort by that instead) so a
  // project's several competitor rows land next to each other instead of interleaved by whatever
  // order the API returned them in.
  const [sort, setSort] = useState<SortState>({ key: "project_name", dir: "asc" });
  const [openFilterColumn, setOpenFilterColumn] = useState<string | null>(null);

  const [dateFilter, setDateFilter] = useState<DateRange>({ from: "", to: "" });
  const [countyFilter, setCountyFilter] = useState<Set<string>>(new Set());
  const [stateFilter, setStateFilter] = useState<Set<string>>(new Set());
  const [bidderFilter, setBidderFilter] = useState<Set<string>>(new Set());
  const [amountFilter, setAmountFilter] = useState<NumRange>({ min: "", max: "" });
  const [rankFilter, setRankFilter] = useState<NumRange>({ min: "", max: "" });
  const [winnerFilter, setWinnerFilter] = useState<Set<WinnerOption>>(new Set());

  const cycleSort = (key: SortKey) => {
    setSort((prev) => {
      if (prev.key !== key) return { key, dir: "asc" };
      if (prev.dir === "asc") return { key, dir: "desc" };
      return { key: null, dir: "asc" };
    });
    setPage(0);
  };

  // results, not projects — this store also holds an unrelated "missing results" projects[] array.
  const uniqueCounties = useMemo(() => uniqueValues(store.results, (r) => r.county), [store.results]);
  const uniqueStates = useMemo(() => uniqueValues(store.results, (r) => r.state), [store.results]);
  const uniqueBidders = useMemo(() => uniqueValues(store.results, (r) => r.raw_bidder_name), [store.results]);

  const hasActiveFilters =
    Boolean(store.resultsSearch) ||
    Boolean(dateFilter.from || dateFilter.to) ||
    countyFilter.size > 0 ||
    stateFilter.size > 0 ||
    bidderFilter.size > 0 ||
    Boolean(amountFilter.min || amountFilter.max) ||
    Boolean(rankFilter.min || rankFilter.max) ||
    winnerFilter.size > 0;

  const clearFilters = () => {
    store.setResultsSearch("");
    setDateFilter({ from: "", to: "" });
    setCountyFilter(new Set());
    setStateFilter(new Set());
    setBidderFilter(new Set());
    setAmountFilter({ min: "", max: "" });
    setRankFilter({ min: "", max: "" });
    setWinnerFilter(new Set());
    setPage(0);
  };

  const filteredSorted = useMemo(() => {
    const q = store.resultsSearch.trim().toLowerCase();
    let rows = store.results.filter((r) => {
      if (
        q &&
        !(
          r.project_name?.toLowerCase().includes(q) ||
          r.county?.toLowerCase().includes(q) ||
          r.raw_bidder_name.toLowerCase().includes(q)
        )
      )
        return false;
      if (!inDateRange(r.bid_date, dateFilter)) return false;
      if (countyFilter.size > 0 && !countyFilter.has(bucket(r.county))) return false;
      if (stateFilter.size > 0 && !stateFilter.has(bucket(r.state))) return false;
      if (bidderFilter.size > 0 && !bidderFilter.has(r.raw_bidder_name)) return false;
      if (!inRange(r.bid_amount, amountFilter)) return false;
      if (!inRange(r.bid_rank, rankFilter)) return false;
      if (winnerFilter.size > 0 && !winnerFilter.has(r.did_win ? "Winner" : "Not winner")) return false;
      return true;
    });
    if (sort.key) {
      rows = [...rows].sort(SORTERS[sort.key](sort.dir));
    }
    return rows;
  }, [store.results, store.resultsSearch, dateFilter, countyFilter, stateFilter, bidderFilter, amountFilter, rankFilter, winnerFilter, sort]);

  const pageCount = Math.max(1, Math.ceil(filteredSorted.length / PAGE_SIZE));
  const pageRows = useMemo(
    () => filteredSorted.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [filteredSorted, page],
  );

  const filterMenuProps = { openFilterColumn, setOpenFilterColumn };

  return (
    <Glass className="p-3">
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <div className="flex max-w-sm flex-1 items-center gap-2 rounded-lg border border-black/10 bg-white/70 px-2.5 py-1.5">
          <Search className="h-3.5 w-3.5 text-muted-foreground" />
          <input
            value={store.resultsSearch}
            onChange={(e) => {
              store.setResultsSearch(e.target.value);
              setPage(0);
            }}
            placeholder="Search project, county, or bidder…"
            className="w-full bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {hasActiveFilters && (
            <button onClick={clearFilters} className="text-[11px] text-muted-foreground hover:text-foreground">
              Clear filters
            </button>
          )}
          <span className="text-[11px] text-muted-foreground">
            {store.loadingResults
              ? "Loading…"
              : filteredSorted.length === store.results.length
                ? `${store.results.length.toLocaleString()} results`
                : `${filteredSorted.length.toLocaleString()} of ${store.results.length.toLocaleString()} results`}
          </span>
        </div>
      </div>

      {store.resultsError && (
        <p className="mb-2 rounded-lg bg-[var(--negative)]/8 px-3 py-2 text-[12px] text-[var(--negative)]">
          {store.resultsError}
        </p>
      )}

      <div className="max-h-[560px] overflow-auto rounded-xl border border-black/5">
        <table className="w-full border-collapse text-[12.5px]">
          <thead className="sticky top-0 z-10 bg-card shadow-[0_1px_0_rgba(0,0,0,0.08)]">
            <tr className="text-left text-[10.5px] uppercase tracking-wide text-muted-foreground">
              <SortableTh label="Bid date" sortKey="bid_date" sort={sort} onSort={cycleSort}>
                <FilterMenu columnKey="bid_date" active={Boolean(dateFilter.from || dateFilter.to)} {...filterMenuProps}>
                  <DateRangePanel value={dateFilter} onChange={(v) => { setDateFilter(v); setPage(0); }} />
                </FilterMenu>
              </SortableTh>
              <SortableTh label="Project" sortKey="project_name" sort={sort} onSort={cycleSort} />
              <SortableTh label="County / State" sortKey="county_state" sort={sort} onSort={cycleSort}>
                <FilterMenu columnKey="county_state" active={countyFilter.size > 0 || stateFilter.size > 0} {...filterMenuProps}>
                  <div className="w-56 p-2">
                    <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">County</p>
                    <CheckboxList options={uniqueCounties} selected={countyFilter} onChange={(v) => { setCountyFilter(v); setPage(0); }} />
                    <div className="my-2 border-t border-black/5" />
                    <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">State</p>
                    <CheckboxList options={uniqueStates} selected={stateFilter} onChange={(v) => { setStateFilter(v); setPage(0); }} searchable={false} />
                  </div>
                </FilterMenu>
              </SortableTh>
              <SortableTh label="Bidder" sortKey="raw_bidder_name" sort={sort} onSort={cycleSort}>
                <FilterMenu columnKey="raw_bidder_name" active={bidderFilter.size > 0} {...filterMenuProps}>
                  <div className="w-56 p-2">
                    <CheckboxList options={uniqueBidders} selected={bidderFilter} onChange={(v) => { setBidderFilter(v); setPage(0); }} />
                  </div>
                </FilterMenu>
              </SortableTh>
              <SortableTh label="Bid amount" sortKey="bid_amount" sort={sort} onSort={cycleSort} align="right">
                <FilterMenu columnKey="bid_amount" active={Boolean(amountFilter.min || amountFilter.max)} {...filterMenuProps}>
                  <NumberRangePanel value={amountFilter} onChange={(v) => { setAmountFilter(v); setPage(0); }} />
                </FilterMenu>
              </SortableTh>
              <SortableTh label="Rank" sortKey="bid_rank" sort={sort} onSort={cycleSort} align="center">
                <FilterMenu columnKey="bid_rank" active={Boolean(rankFilter.min || rankFilter.max)} {...filterMenuProps}>
                  <NumberRangePanel value={rankFilter} onChange={(v) => { setRankFilter(v); setPage(0); }} />
                </FilterMenu>
              </SortableTh>
              <SortableTh label="Winner" sortKey="did_win" sort={sort} onSort={cycleSort} align="center">
                <FilterMenu columnKey="did_win" active={winnerFilter.size > 0} {...filterMenuProps}>
                  <div className="w-40 p-2">
                    <CheckboxList
                      options={["Winner", "Not winner"]}
                      selected={winnerFilter}
                      onChange={(v) => { setWinnerFilter(v as Set<WinnerOption>); setPage(0); }}
                      searchable={false}
                    />
                  </div>
                </FilterMenu>
              </SortableTh>
            </tr>
          </thead>
          <tbody>
            {!store.loadingResults && pageRows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-muted-foreground">
                  No results found.
                </td>
              </tr>
            )}
            {pageRows.map((r) => (
              <ResultRow key={`${r.project_natural_key}::${r.competitor_unit_id}`} row={r} store={store} />
            ))}
          </tbody>
        </table>
      </div>

      {pageCount > 1 && (
        <div className="mt-2.5 flex items-center justify-end gap-2 text-[12px]">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded-md px-2 py-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
          >
            Prev
          </button>
          <span className="text-muted-foreground">
            Page {page + 1} of {pageCount}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={page >= pageCount - 1}
            className="rounded-md px-2 py-1 text-muted-foreground hover:text-foreground disabled:opacity-30"
          >
            Next
          </button>
        </div>
      )}
    </Glass>
  );
}

function ResultRow({ row, store }: { row: BidResultRow; store: Store }) {
  const [saving, setSaving] = useState<"" | "name" | "amount">("");
  // Inputs below are uncontrolled (defaultValue + a remount key) rather than mirrored into local
  // state: the server is the source of truth (a sibling edit on the same project can recompute
  // this row's bid_rank/bid_amount), and bumping the reset key forces the DOM value back to the
  // server's on a rejected edit without needing a setState-in-effect resync.
  const [nameResetKey, setNameResetKey] = useState(0);
  const [amountResetKey, setAmountResetKey] = useState(0);

  const commitName = async (raw: string) => {
    const trimmed = raw.trim();
    if (!trimmed || trimmed === row.raw_bidder_name) {
      setNameResetKey((k) => k + 1);
      return;
    }
    setSaving("name");
    const ok = await store.updateResult(row.project_natural_key, row.competitor_unit_id, {
      raw_bidder_name: trimmed,
    });
    if (!ok) setNameResetKey((k) => k + 1);
    setSaving("");
  };

  const commitAmount = async (raw: string) => {
    const n = Number(raw);
    if (!raw || Number.isNaN(n) || n <= 0 || n === row.bid_amount) {
      setAmountResetKey((k) => k + 1);
      return;
    }
    setSaving("amount");
    const ok = await store.updateResult(row.project_natural_key, row.competitor_unit_id, { bid_amount: n });
    if (!ok) setAmountResetKey((k) => k + 1);
    setSaving("");
  };

  return (
    <tr className="border-t border-black/5 hover:bg-black/[0.02]">
      <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">{dateStr(row.bid_date)}</td>
      <td
        className="max-w-[220px] truncate px-3 py-1.5 font-medium"
        title={row.project_name ?? row.project_natural_key}
      >
        {row.project_name || row.project_natural_key}
      </td>
      <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">
        {row.county}, {row.state}
      </td>
      <td className="px-3 py-1.5">
        <input
          key={`name-${nameResetKey}`}
          defaultValue={row.raw_bidder_name}
          onBlur={(e) => commitName(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          disabled={saving === "name"}
          className="w-full min-w-[140px] rounded-md border border-transparent bg-transparent px-1.5 py-0.5 outline-none focus:border-primary/40 focus:bg-white/70"
        />
        {row.current_comp_name && row.current_comp_name !== row.raw_bidder_name && (
          <p className="px-1.5 text-[10.5px] text-muted-foreground" title="This competitor has since been consolidated onto a new canonical name.">
            now: {row.current_comp_name}
          </p>
        )}
      </td>
      <td className="px-3 py-1.5 text-right">
        <input
          key={`amount-${amountResetKey}`}
          defaultValue={row.bid_amount}
          onBlur={(e) => commitAmount(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          disabled={saving === "amount"}
          inputMode="decimal"
          className="w-28 rounded-md border border-transparent bg-transparent px-1.5 py-0.5 text-right font-mono outline-none focus:border-primary/40 focus:bg-white/70"
        />
      </td>
      <td className="px-3 py-1.5 text-center font-mono text-muted-foreground">{row.bid_rank ?? "—"}</td>
      <td className="px-3 py-1.5 text-center">
        <div
          title={row.did_win ? "Winner — lowest bid" : undefined}
          className={cn(
            "inline-grid h-6 w-6 place-items-center rounded-full border",
            row.did_win
              ? "border-[var(--positive)] bg-[var(--positive)] text-white"
              : "border-black/15 text-transparent",
          )}
        >
          <Trophy className="h-3 w-3" />
        </div>
      </td>
    </tr>
  );
}

// ── Shared-within-this-file sort/filter UI pieces ────────────────────────────

function SortableTh({
  label,
  sortKey,
  sort,
  onSort,
  align = "left",
  children,
}: {
  label: string;
  sortKey?: SortKey;
  sort: SortState;
  onSort: (key: SortKey) => void;
  align?: "left" | "right" | "center";
  children?: React.ReactNode;
}) {
  const active = sortKey != null && sort.key === sortKey;
  return (
    <th className={cn("px-3 py-2 font-medium", align === "right" && "text-right", align === "center" && "text-center")}>
      <div className={cn("flex items-center gap-1", align === "right" && "justify-end", align === "center" && "justify-center")}>
        {sortKey ? (
          <button
            type="button"
            onClick={() => onSort(sortKey)}
            className="flex items-center gap-0.5 hover:text-foreground"
          >
            {label}
            {active ? (
              sort.dir === "asc" ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronsUpDown className="h-3 w-3 opacity-30" />
            )}
          </button>
        ) : (
          <span>{label}</span>
        )}
        {children}
      </div>
    </th>
  );
}

function FilterMenu({
  columnKey,
  openFilterColumn,
  setOpenFilterColumn,
  active,
  children,
}: {
  columnKey: string;
  openFilterColumn: string | null;
  setOpenFilterColumn: (k: string | null) => void;
  active: boolean;
  children: React.ReactNode;
}) {
  const isOpen = openFilterColumn === columnKey;
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpenFilterColumn(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenFilterColumn(null);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [isOpen, setOpenFilterColumn]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpenFilterColumn(isOpen ? null : columnKey)}
        className={cn("rounded p-0.5 normal-case hover:bg-black/5", active ? "text-primary" : "text-muted-foreground/50")}
        title="Filter"
      >
        <ListFilter className="h-3 w-3" />
      </button>
      {isOpen && (
        <div
          className="absolute left-0 z-20 mt-1 rounded-lg border border-black/10 bg-white normal-case shadow-lg"
          onClick={(e) => e.stopPropagation()}
        >
          {children}
        </div>
      )}
    </div>
  );
}

function CheckboxList({
  options,
  selected,
  onChange,
  searchable = true,
}: {
  options: string[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  searchable?: boolean;
}) {
  const [query, setQuery] = useState("");
  const filtered = searchable && query ? options.filter((o) => o.toLowerCase().includes(query.toLowerCase())) : options;

  const toggle = (opt: string) => {
    const next = new Set(selected);
    if (next.has(opt)) next.delete(opt);
    else next.add(opt);
    onChange(next);
  };

  return (
    <div>
      {searchable && options.length > 8 && (
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search…"
          className="mb-1.5 w-full rounded-md border border-black/10 bg-white/70 px-2 py-1 text-[12px] outline-none focus:border-primary/50"
        />
      )}
      <div className="mb-1 flex items-center justify-between text-[11px]">
        <button type="button" onClick={() => onChange(new Set(options))} className="text-primary hover:underline">
          Select all
        </button>
        <button type="button" onClick={() => onChange(new Set())} className="text-muted-foreground hover:underline">
          Clear
        </button>
      </div>
      <div className="max-h-40 overflow-auto">
        {filtered.length === 0 && <p className="px-1 py-2 text-[11.5px] text-muted-foreground">No matches.</p>}
        {filtered.map((opt) => (
          <label key={opt} className="flex cursor-pointer items-center gap-1.5 rounded px-1 py-1 text-[12px] hover:bg-black/[0.03]">
            <input type="checkbox" checked={selected.has(opt)} onChange={() => toggle(opt)} className="h-3 w-3 accent-primary" />
            <span className="truncate">{opt}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function NumberRangePanel({ value, onChange }: { value: NumRange; onChange: (next: NumRange) => void }) {
  const [draft, setDraft] = useState(value);
  const [prevValue, setPrevValue] = useState(value);
  if (value !== prevValue) {
    setPrevValue(value);
    setDraft(value);
  }
  const commit = () => onChange(draft);
  return (
    <div className="w-40 space-y-1.5 p-2.5">
      <label className="block text-[11px] text-muted-foreground">
        Min
        <input
          value={draft.min}
          onChange={(e) => setDraft((d) => ({ ...d, min: e.target.value }))}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          inputMode="decimal"
          className="mt-0.5 w-full rounded-md border border-black/10 bg-white/70 px-2 py-1 text-[12px] outline-none focus:border-primary/50"
        />
      </label>
      <label className="block text-[11px] text-muted-foreground">
        Max
        <input
          value={draft.max}
          onChange={(e) => setDraft((d) => ({ ...d, max: e.target.value }))}
          onBlur={commit}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
          inputMode="decimal"
          className="mt-0.5 w-full rounded-md border border-black/10 bg-white/70 px-2 py-1 text-[12px] outline-none focus:border-primary/50"
        />
      </label>
    </div>
  );
}

function DateRangePanel({ value, onChange }: { value: DateRange; onChange: (next: DateRange) => void }) {
  const [draft, setDraft] = useState(value);
  const [prevValue, setPrevValue] = useState(value);
  if (value !== prevValue) {
    setPrevValue(value);
    setDraft(value);
  }
  const commit = () => onChange(draft);
  return (
    <div className="w-44 space-y-1.5 p-2.5">
      <label className="block text-[11px] text-muted-foreground">
        From
        <input
          type="date"
          value={draft.from}
          onChange={(e) => setDraft((d) => ({ ...d, from: e.target.value }))}
          onBlur={commit}
          className="mt-0.5 w-full rounded-md border border-black/10 bg-white/70 px-2 py-1 text-[12px] outline-none focus:border-primary/50"
        />
      </label>
      <label className="block text-[11px] text-muted-foreground">
        To
        <input
          type="date"
          value={draft.to}
          onChange={(e) => setDraft((d) => ({ ...d, to: e.target.value }))}
          onBlur={commit}
          className="mt-0.5 w-full rounded-md border border-black/10 bg-white/70 px-2 py-1 text-[12px] outline-none focus:border-primary/50"
        />
      </label>
    </div>
  );
}
