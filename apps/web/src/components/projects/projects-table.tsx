"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, ChevronsUpDown, ListFilter, Search } from "lucide-react";
import { Glass, Chip } from "@/components/kit";
import { cn } from "@/lib/utils";
import { MATERIAL_FIELDS, type MaterialField, type Project, type useProjectsStore } from "./use-projects-store";

const PAGE_SIZE = 100;
const BLANK = "(Blanks)";

const dateStr = (d: string | null) =>
  d
    ? new Date(`${d}T00:00:00`).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" })
    : "—";

const MATERIAL_COLUMNS: { field: MaterialField; label: string }[] = [
  { field: "mix_tons", label: "Mix (tons)" },
  { field: "grading_yards", label: "Grading (yds)" },
  { field: "base_tons", label: "Base (tons)" },
  { field: "shldr_tons", label: "Shldr (tons)" },
  { field: "mill_sy", label: "Mill (SY)" },
  { field: "crush_tons", label: "Crush (tons)" },
  { field: "stock_tons", label: "Stock (tons)" },
];

// ── Generic sort/filter helpers (kept local to this file by design) ─────────

type SortDir = "asc" | "desc";
type SortKey = "bid_date" | "project_name" | "county_state" | "project_type" | MaterialField;
type SortState = { key: SortKey | null; dir: SortDir };
type NumRange = { min: string; max: string };
type DateRange = { from: string; to: string };

const bucket = (v: string | null) => (v && v.trim() ? v : BLANK);

function uniqueValues(rows: Project[], getValue: (row: Project) => string | null): string[] {
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

const emptyMaterialFilters = () =>
  Object.fromEntries(MATERIAL_FIELDS.map((f) => [f, { min: "", max: "" }])) as Record<MaterialField, NumRange>;

const SORTERS: Record<SortKey, (dir: SortDir) => (a: Project, b: Project) => number> = {
  bid_date: (dir) => makeComparator((p: Project) => p.bid_date, dir),
  project_name: (dir) => makeComparator((p: Project) => p.project_name, dir),
  county_state: (dir) => (a, b) => {
    const c = makeComparator((p: Project) => p.county, dir)(a, b);
    return c !== 0 ? c : makeComparator((p: Project) => p.state, dir)(a, b);
  },
  project_type: (dir) => makeComparator((p: Project) => p.project_type, dir),
  ...Object.fromEntries(
    MATERIAL_FIELDS.map((f) => [f, (dir: SortDir) => makeComparator((p: Project) => p[f], dir)]),
  ),
} as Record<SortKey, (dir: SortDir) => (a: Project, b: Project) => number>;

type Store = ReturnType<typeof useProjectsStore>;

export function ProjectsTable({ store }: { store: Store }) {
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<SortState>({ key: null, dir: "asc" });
  const [openFilterColumn, setOpenFilterColumn] = useState<string | null>(null);

  const [dateFilter, setDateFilter] = useState<DateRange>({ from: "", to: "" });
  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set());
  const [countyFilter, setCountyFilter] = useState<Set<string>>(new Set());
  const [stateFilter, setStateFilter] = useState<Set<string>>(new Set());
  const [materialFilters, setMaterialFilters] = useState<Record<MaterialField, NumRange>>(emptyMaterialFilters);

  const cycleSort = (key: SortKey) => {
    setSort((prev) => {
      if (prev.key !== key) return { key, dir: "asc" };
      if (prev.dir === "asc") return { key, dir: "desc" };
      return { key: null, dir: "asc" };
    });
    setPage(0);
  };

  const uniqueTypes = useMemo(() => uniqueValues(store.projects, (p) => p.project_type), [store.projects]);
  const uniqueCounties = useMemo(() => uniqueValues(store.projects, (p) => p.county), [store.projects]);
  const uniqueStates = useMemo(() => uniqueValues(store.projects, (p) => p.state), [store.projects]);

  const hasActiveFilters =
    Boolean(store.search) ||
    Boolean(dateFilter.from || dateFilter.to) ||
    typeFilter.size > 0 ||
    countyFilter.size > 0 ||
    stateFilter.size > 0 ||
    MATERIAL_FIELDS.some((f) => materialFilters[f].min || materialFilters[f].max);

  const clearFilters = () => {
    store.setSearch("");
    setDateFilter({ from: "", to: "" });
    setTypeFilter(new Set());
    setCountyFilter(new Set());
    setStateFilter(new Set());
    setMaterialFilters(emptyMaterialFilters());
    setPage(0);
  };

  const filteredSorted = useMemo(() => {
    const q = store.search.trim().toLowerCase();
    let rows = store.projects.filter((p) => {
      if (q && !(p.project_name?.toLowerCase().includes(q) || p.county?.toLowerCase().includes(q))) return false;
      if (!inDateRange(p.bid_date, dateFilter)) return false;
      if (typeFilter.size > 0 && !typeFilter.has(bucket(p.project_type))) return false;
      if (countyFilter.size > 0 && !countyFilter.has(bucket(p.county))) return false;
      if (stateFilter.size > 0 && !stateFilter.has(bucket(p.state))) return false;
      for (const f of MATERIAL_FIELDS) {
        if (!inRange(p[f], materialFilters[f])) return false;
      }
      return true;
    });
    if (sort.key) {
      rows = [...rows].sort(SORTERS[sort.key](sort.dir));
    }
    return rows;
  }, [store.projects, store.search, dateFilter, typeFilter, countyFilter, stateFilter, materialFilters, sort]);

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
            value={store.search}
            onChange={(e) => {
              store.setSearch(e.target.value);
              setPage(0);
            }}
            placeholder="Search project or county…"
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
            {store.loading
              ? "Loading…"
              : filteredSorted.length === store.projects.length
                ? `${store.projects.length.toLocaleString()} projects`
                : `${filteredSorted.length.toLocaleString()} of ${store.projects.length.toLocaleString()} projects`}
          </span>
        </div>
      </div>

      {store.error && (
        <p className="mb-2 rounded-lg bg-[var(--negative)]/8 px-3 py-2 text-[12px] text-[var(--negative)]">
          {store.error}
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
              <SortableTh label="Type" sortKey="project_type" sort={sort} onSort={cycleSort}>
                <FilterMenu columnKey="project_type" active={typeFilter.size > 0} {...filterMenuProps}>
                  <div className="w-52 p-2">
                    <CheckboxList options={uniqueTypes} selected={typeFilter} onChange={(v) => { setTypeFilter(v); setPage(0); }} />
                  </div>
                </FilterMenu>
              </SortableTh>
              {MATERIAL_COLUMNS.map((c) => (
                <SortableTh key={c.field} label={c.label} sortKey={c.field} sort={sort} onSort={cycleSort} align="right">
                  <FilterMenu
                    columnKey={c.field}
                    active={Boolean(materialFilters[c.field].min || materialFilters[c.field].max)}
                    {...filterMenuProps}
                  >
                    <NumberRangePanel
                      value={materialFilters[c.field]}
                      onChange={(v) => {
                        setMaterialFilters((prev) => ({ ...prev, [c.field]: v }));
                        setPage(0);
                      }}
                    />
                  </FilterMenu>
                </SortableTh>
              ))}
            </tr>
          </thead>
          <tbody>
            {!store.loading && pageRows.length === 0 && (
              <tr>
                <td colSpan={4 + MATERIAL_COLUMNS.length} className="px-3 py-8 text-center text-muted-foreground">
                  No projects found.
                </td>
              </tr>
            )}
            {pageRows.map((p) => (
              <ProjectRow key={p.project_natural_key} project={p} store={store} />
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

function ProjectRow({ project, store }: { project: Project; store: Store }) {
  return (
    <tr className="border-t border-black/5 hover:bg-black/[0.02]">
      <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">{dateStr(project.bid_date)}</td>
      <td
        className="max-w-[220px] truncate px-3 py-1.5 font-medium"
        title={project.project_natural_key}
      >
        {project.project_name || project.project_natural_key}
      </td>
      <td className="whitespace-nowrap px-3 py-1.5 text-muted-foreground">
        {project.county}, {project.state}
      </td>
      <td className="whitespace-nowrap px-3 py-1.5">
        {project.project_type ? <Chip tone="neutral">{project.project_type}</Chip> : <span className="text-muted-foreground">—</span>}
      </td>
      {MATERIAL_COLUMNS.map((c) => (
        <td key={c.field} className="px-3 py-1.5 text-right">
          <MaterialCell project={project} field={c.field} store={store} />
        </td>
      ))}
    </tr>
  );
}

function MaterialCell({ project, field, store }: { project: Project; field: MaterialField; store: Store }) {
  const [resetKey, setResetKey] = useState(0);
  const [saving, setSaving] = useState(false);
  const current = project[field];

  const commit = async (raw: string) => {
    const trimmed = raw.trim();
    const parsed = trimmed === "" ? null : Number(trimmed);
    if (parsed !== null && (Number.isNaN(parsed) || parsed < 0)) {
      setResetKey((k) => k + 1); // reject: snap back to the server value
      return;
    }
    if (parsed === current) {
      setResetKey((k) => k + 1); // no-op edit, still resync the DOM to a clean formatted value
      return;
    }
    setSaving(true);
    const ok = await store.updateMaterials(project.project_natural_key, { [field]: parsed });
    if (!ok) setResetKey((k) => k + 1);
    setSaving(false);
  };

  return (
    <input
      key={`${field}-${resetKey}`}
      defaultValue={current ?? ""}
      onBlur={(e) => commit(e.target.value)}
      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
      disabled={saving}
      inputMode="decimal"
      placeholder="—"
      className="w-20 rounded-md border border-transparent bg-transparent px-1.5 py-0.5 text-right font-mono outline-none focus:border-primary/40 focus:bg-white/70 disabled:opacity-60"
    />
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
  align?: "left" | "right";
  children?: React.ReactNode;
}) {
  const active = sortKey != null && sort.key === sortKey;
  return (
    <th className={cn("px-3 py-2 font-medium", align === "right" && "text-right")}>
      <div className={cn("flex items-center gap-1", align === "right" && "justify-end")}>
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
