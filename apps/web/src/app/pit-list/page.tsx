"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Script from "next/script";
import {
  Mountain, Plus, Pencil, Trash2, Check, X, Search, AlertTriangle, MapPin, Download,
  ChevronDown, ChevronUp, ChevronsUpDown, ListFilter, LocateFixed, Navigation,
} from "lucide-react";
import { Glass, Eyebrow, SectionTitle, Chip } from "@/components/kit";
import { cn } from "@/lib/utils";
import { downloadText } from "@/lib/report";
import { usePitListStore, emptyPitForm, type Pit, type PitForm, type PitWithDistance } from "@/components/pit-list/use-pit-list-store";
import { AccessCompanyPicker } from "@/components/pit-list/access-company-picker";
import { PitMap, type MapOrigin } from "@/components/pit-list/pit-map";
import { ProjectMidpointPicker, type ProjectHit } from "@/components/pit-list/project-midpoint-picker";
import { haversineMiles } from "@/lib/geo";

declare global {
  interface Window {
    google?: any; // eslint-disable-line @typescript-eslint/no-explicit-any
  }
}

const GOOGLE_MAPS_API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || "";
const HAS_MAPS_KEY = Boolean(GOOGLE_MAPS_API_KEY);
const ACCESS_TYPES = ["open", "unknown", "client", "competitor", "closed", "knife_river_pending"];
const PAGE_SIZE = 100;
const BLANK = "(Blanks)";

function mapsLinkFor(lat: number, lon: number) {
  return `https://www.google.com/maps?q=${lat},${lon}`;
}

// ── Generic sort/filter helpers (kept local to this file by design) ─────────

type SortDir = "asc" | "desc";
type SortKey = "name" | "county" | "state" | "rating" | "access_type" | "access_company" | "distance";
type SortState = { key: SortKey | null; dir: SortDir };
type NumRange = { min: string; max: string };

const bucket = (v: string | null) => (v && v.trim() ? v : BLANK);

function uniqueValues(rows: Pit[], getValue: (row: Pit) => string | null): string[] {
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

const SORTERS: Record<SortKey, (dir: SortDir) => (a: PitWithDistance, b: PitWithDistance) => number> = {
  name: (dir) => makeComparator((p: PitWithDistance) => p.name, dir),
  county: (dir) => makeComparator((p: PitWithDistance) => p.county, dir),
  state: (dir) => makeComparator((p: PitWithDistance) => p.state, dir),
  rating: (dir) => makeComparator((p: PitWithDistance) => p.rating, dir),
  access_type: (dir) => makeComparator((p: PitWithDistance) => p.access_type, dir),
  access_company: (dir) => makeComparator((p: PitWithDistance) => p.access_company, dir),
  distance: (dir) => makeComparator((p: PitWithDistance) => p.distanceMiles, dir),
};

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
    <th className={cn("px-2.5 py-2 font-medium", align === "right" && "text-right")}>
      <div className={cn("flex items-center gap-1", align === "right" && "justify-end")}>
        {sortKey ? (
          <button type="button" onClick={() => onSort(sortKey)} className="flex items-center gap-0.5 hover:text-foreground">
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

export default function PitListPage() {
  const store = usePitListStore();
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState<PitForm>(emptyPitForm());
  const [accessCompanyValid, setAccessCompanyValid] = useState(false);
  const [mapsReady, setMapsReady] = useState(false);

  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<SortState>({ key: null, dir: "asc" });
  const [openFilterColumn, setOpenFilterColumn] = useState<string | null>(null);
  const [countyFilter, setCountyFilter] = useState<Set<string>>(new Set());
  const [stateFilter, setStateFilter] = useState<Set<string>>(new Set());
  // Rating 1 makes up the bulk of this table (~68% of all pits) and was the main cost of rendering
  // every pit as a map marker; default it filtered out so both the map and table start manageable.
  // Still just the normal Rating column filter underneath — "Clear filters" or editing the Min box
  // brings rating-1 pits back.
  const [ratingFilter, setRatingFilter] = useState<NumRange>({ min: "2", max: "" });
  const [accessTypeFilter, setAccessTypeFilter] = useState<Set<string>>(new Set());
  const [accessCompanyFilter, setAccessCompanyFilter] = useState<Set<string>>(new Set());

  // "Nearest pits" search — an origin set either by picking a bid project's midpoint or by typing
  // in a raw lat/long. Drives a computed Distance column/sort; does not hide rows on its own.
  const [origin, setOrigin] = useState<MapOrigin | null>(null);
  const [coordLat, setCoordLat] = useState("");
  const [coordLon, setCoordLon] = useState("");
  const [coordError, setCoordError] = useState<string | null>(null);

  const applyCoordOrigin = () => {
    const lat = parseFloat(coordLat);
    const lon = parseFloat(coordLon);
    if (Number.isNaN(lat) || Number.isNaN(lon)) {
      setCoordError("Enter a numeric latitude and longitude.");
      return;
    }
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      setCoordError("Latitude must be between -90 and 90; longitude between -180 and 180.");
      return;
    }
    setCoordError(null);
    setOrigin({ lat, lon, label: `${lat.toFixed(4)}, ${lon.toFixed(4)}` });
    setPage(0);
  };

  const applyProjectOrigin = (project: ProjectHit) => {
    if (project.project_latitude == null || project.project_longitude == null) return;
    setCoordError(null);
    setOrigin({
      lat: project.project_latitude,
      lon: project.project_longitude,
      label: project.project_name || project.project_natural_key,
    });
    setPage(0);
  };

  const clearOrigin = () => {
    setOrigin(null);
    setCoordLat("");
    setCoordLon("");
    setCoordError(null);
  };

  useEffect(() => {
    store.fetchPits();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const set = (patch: Partial<PitForm>) => setForm((p) => ({ ...p, ...patch }));

  const cycleSort = (key: SortKey) => {
    setSort((prev) => {
      if (prev.key !== key) return { key, dir: "asc" };
      if (prev.dir === "asc") return { key, dir: "desc" };
      return { key: null, dir: "asc" };
    });
    setPage(0);
  };

  const uniqueCounties = useMemo(() => uniqueValues(store.pits, (p) => p.county), [store.pits]);
  const uniqueStates = useMemo(() => uniqueValues(store.pits, (p) => p.state), [store.pits]);
  const uniqueAccessCompanies = useMemo(() => uniqueValues(store.pits, (p) => p.access_company), [store.pits]);

  const hasActiveFilters =
    Boolean(store.search) ||
    countyFilter.size > 0 ||
    stateFilter.size > 0 ||
    Boolean(ratingFilter.min || ratingFilter.max) ||
    accessTypeFilter.size > 0 ||
    accessCompanyFilter.size > 0;

  const clearFilters = () => {
    store.setSearch("");
    setCountyFilter(new Set());
    setStateFilter(new Set());
    setRatingFilter({ min: "", max: "" });
    setAccessTypeFilter(new Set());
    setAccessCompanyFilter(new Set());
    setPage(0);
  };

  const pitsWithDistance = useMemo<PitWithDistance[]>(() => {
    if (!origin) return store.pits.map((p) => ({ ...p, distanceMiles: null }));
    return store.pits.map((p) => ({
      ...p,
      distanceMiles: haversineMiles(origin.lat, origin.lon, p.latitude, p.longitude),
    }));
  }, [store.pits, origin]);

  const filteredSorted = useMemo(() => {
    const q = store.search.trim().toLowerCase();
    let rows = pitsWithDistance.filter((p) => {
      if (q && !(p.name?.toLowerCase().includes(q) || p.county?.toLowerCase().includes(q) || p.state?.toLowerCase().includes(q))) return false;
      if (countyFilter.size > 0 && !countyFilter.has(bucket(p.county))) return false;
      if (stateFilter.size > 0 && !stateFilter.has(bucket(p.state))) return false;
      if (!inRange(p.rating, ratingFilter)) return false;
      if (accessTypeFilter.size > 0 && !accessTypeFilter.has(bucket(p.access_type))) return false;
      if (accessCompanyFilter.size > 0 && !accessCompanyFilter.has(bucket(p.access_company))) return false;
      return true;
    });
    if (origin) {
      // Once an origin is set, narrow to the 10 physically nearest pits before applying any
      // display sort, so "closest 10" always means actual distance regardless of which column
      // the table is currently sorted by.
      rows = [...rows].sort(SORTERS.distance("asc")).slice(0, 10);
    }
    if (sort.key) {
      rows = [...rows].sort(SORTERS[sort.key](sort.dir));
    } else if (origin) {
      // Default to nearest-first once an origin is set, until the user picks a different column.
      rows = [...rows].sort(SORTERS.distance("asc"));
    }
    return rows;
  }, [pitsWithDistance, store.search, countyFilter, stateFilter, ratingFilter, accessTypeFilter, accessCompanyFilter, sort, origin]);

  const pageCount = Math.max(1, Math.ceil(filteredSorted.length / PAGE_SIZE));
  const pageRows = useMemo(
    () => filteredSorted.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE),
    [filteredSorted, page],
  );

  const filterMenuProps = { openFilterColumn, setOpenFilterColumn };

  // Auto-populate county/state from lat/long via the Maps JS Geocoder — fires once both parse as
  // numbers, called from onBlur on either coordinate field.
  const geocode = () => {
    if (!mapsReady || !window.google) return;
    const lat = parseFloat(form.latitude);
    const lng = parseFloat(form.longitude);
    if (Number.isNaN(lat) || Number.isNaN(lng)) return;
    const geocoder = new window.google.maps.Geocoder();
    geocoder.geocode({ location: { lat, lng } }, (results: any, status: string) => { // eslint-disable-line @typescript-eslint/no-explicit-any
      if (status !== "OK" || !results?.[0]) return;
      let county = "";
      let state = "";
      for (const comp of results[0].address_components) {
        if (comp.types.includes("administrative_area_level_2")) county = comp.long_name.replace(/ County$/i, "");
        if (comp.types.includes("administrative_area_level_1")) state = comp.short_name;
      }
      if (county || state) set({ county: county || form.county, state: state || form.state });
    });
  };

  const submitAdd = async (force = false) => {
    if (form.access_company.trim() && !accessCompanyValid) {
      store.setError("Access company must match a name in the competitor registry.");
      return;
    }
    const ok = await store.createPit(form, force);
    if (ok) {
      setForm(emptyPitForm());
      setAccessCompanyValid(false);
      setShowAdd(false);
    }
  };

  const exportCsv = () => {
    const cols: (keyof PitWithDistance)[] = ["name", "county", "state", "latitude", "longitude", "rating", "access", "access_type", "access_company"];
    if (origin) cols.push("distanceMiles");
    const esc = (v: unknown) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    // Exports the currently filtered/sorted view, not the full unfiltered table.
    const rows = [cols, ...filteredSorted.map((p) => cols.map((c) => p[c]))];
    const csv = rows.map((r) => r.map(esc).join(",")).join("\n");
    downloadText(`pit-list-${new Date().toISOString().slice(0, 10)}.csv`, csv, "text/csv");
  };

  return (
    <div className="mx-auto max-w-6xl p-6">
      {HAS_MAPS_KEY && (
        <Script
          id="google-maps-script"
          src={`https://maps.googleapis.com/maps/api/js?key=${GOOGLE_MAPS_API_KEY}`}
          strategy="afterInteractive"
          onReady={() => setMapsReady(true)}
        />
      )}

      <Eyebrow>Data · Pit List</Eyebrow>
      <div className="mt-1 flex items-center justify-between">
        <h1 className="font-serif text-2xl tracking-tight">Aggregate pit locations</h1>
        <button
          onClick={() => setShowAdd((s) => !s)}
          className="flex items-center gap-1.5 rounded-xl bg-primary px-3.5 py-2 text-[13px] font-medium text-primary-foreground elev-sm transition-all hover:-translate-y-px hover:elev-md"
        >
          <Plus className="h-4 w-4" /> Add pit
        </button>
      </div>
      <p className="mt-1 max-w-xl text-[13px] text-muted-foreground">
        Feeds the nearest-pit distance features in the competitor-intelligence model.
      </p>

      <Glass className="mt-4 p-3">
        <div className="mb-2 flex items-center justify-between">
          <SectionTitle>Find nearest pits</SectionTitle>
          {origin && (
            <button onClick={clearOrigin} className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground">
              <X className="h-3 w-3" /> Clear
            </button>
          )}
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <span className="mb-1 block text-[10px] uppercase tracking-wide text-muted-foreground">By bid project</span>
            <ProjectMidpointPicker onSelect={applyProjectOrigin} />
          </div>
          <div>
            <span className="mb-1 block text-[10px] uppercase tracking-wide text-muted-foreground">By coordinates</span>
            <div className="flex items-center gap-1.5">
              <input
                value={coordLat}
                onChange={(e) => setCoordLat(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && applyCoordOrigin()}
                placeholder="Latitude"
                inputMode="decimal"
                className={cn(inputCls, "w-full")}
              />
              <input
                value={coordLon}
                onChange={(e) => setCoordLon(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && applyCoordOrigin()}
                placeholder="Longitude"
                inputMode="decimal"
                className={cn(inputCls, "w-full")}
              />
              <button
                onClick={applyCoordOrigin}
                title="Find nearest pits"
                className="flex shrink-0 items-center gap-1 rounded-lg bg-primary px-2.5 py-1.5 text-[12px] font-medium text-primary-foreground"
              >
                <LocateFixed className="h-3.5 w-3.5" /> Find
              </button>
            </div>
          </div>
        </div>
        {coordError && <p className="mt-2 text-[12px] text-[var(--negative)]">{coordError}</p>}
        {origin && (
          <p className="mt-2 flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
            <Navigation className="h-3.5 w-3.5 text-primary" />
            Showing pits nearest to <span className="font-medium text-foreground">{origin.label}</span>
            <span className="font-mono text-[11.5px]">({origin.lat.toFixed(4)}, {origin.lon.toFixed(4)})</span>
          </p>
        )}
      </Glass>

      <div className="mt-4">
        <PitMap pits={filteredSorted} mapsReady={mapsReady} hasKey={HAS_MAPS_KEY} origin={origin} />
      </div>

      {showAdd && (
        <Glass className="mt-4 p-4">
          <SectionTitle>New pit</SectionTitle>
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
            <Field label="Latitude *">
              <input value={form.latitude} onChange={(e) => set({ latitude: e.target.value })} onBlur={geocode} className={inputCls} placeholder="45.6301" />
            </Field>
            <Field label="Longitude *">
              <input value={form.longitude} onChange={(e) => set({ longitude: e.target.value })} onBlur={geocode} className={inputCls} placeholder="-94.2019" />
            </Field>
            <Field label="Name *"><input value={form.name} onChange={(e) => set({ name: e.target.value })} className={inputCls} /></Field>
            <Field label="County *">
              <input value={form.county} onChange={(e) => set({ county: e.target.value })} className={inputCls} placeholder="auto-filled from lat/long" />
            </Field>
            <Field label="State *">
              <input value={form.state} onChange={(e) => set({ state: e.target.value })} className={inputCls} placeholder="auto-filled from lat/long" />
            </Field>
            <Field label="Rating *"><input value={form.rating} onChange={(e) => set({ rating: e.target.value })} className={inputCls} inputMode="numeric" /></Field>
            <Field label="Access (raw owner text) *"><input value={form.access} onChange={(e) => set({ access: e.target.value })} className={inputCls} /></Field>
            <Field label="Access type *">
              <select value={form.access_type} onChange={(e) => set({ access_type: e.target.value })} className={inputCls}>
                {ACCESS_TYPES.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </Field>
            <Field label="Access company *">
              <AccessCompanyPicker
                value={form.access_company}
                onChange={(v) => set({ access_company: v })}
                onValidityChange={setAccessCompanyValid}
              />
            </Field>
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
            <button
              onClick={() => submitAdd(false)}
              disabled={store.saving}
              className="flex items-center gap-1.5 rounded-xl bg-primary px-3.5 py-2 text-[13px] font-medium text-primary-foreground disabled:opacity-60"
            >
              <Check className="h-3.5 w-3.5" /> {store.saving ? "Saving…" : "Save pit"}
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
              onChange={(e) => { store.setSearch(e.target.value); setPage(0); }}
              placeholder="Search name, county, or state…"
              className="w-full bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
            />
          </div>
          {hasActiveFilters && (
            <button onClick={clearFilters} className="shrink-0 text-[11px] text-muted-foreground hover:text-foreground">
              Clear filters
            </button>
          )}
          <span className="shrink-0 text-[11px] text-muted-foreground">
            {store.loading
              ? "Loading…"
              : filteredSorted.length === store.pits.length
                ? `${store.pits.length.toLocaleString()} pits`
                : `${filteredSorted.length.toLocaleString()} of ${store.pits.length.toLocaleString()} pits`}
          </span>
          <button
            onClick={exportCsv}
            className="flex shrink-0 items-center gap-1.5 rounded-lg border border-black/10 px-3 py-1.5 text-[12px] font-medium text-muted-foreground hover:text-foreground"
          >
            <Download className="h-3.5 w-3.5" /> Export CSV
          </button>
        </div>

        <div className="max-h-[560px] overflow-auto rounded-lg">
          <table className="w-full min-w-[900px] border-collapse text-[12.5px]">
            <thead className="sticky top-0 z-10 bg-[var(--background,white)]">
              <tr className="border-b border-black/10 text-left text-[10.5px] uppercase tracking-wide text-muted-foreground">
                <SortableTh label="Name" sortKey="name" sort={sort} onSort={cycleSort} />
                <SortableTh label="County" sortKey="county" sort={sort} onSort={cycleSort}>
                  <FilterMenu columnKey="county" active={countyFilter.size > 0} {...filterMenuProps}>
                    <div className="w-52 p-2">
                      <CheckboxList options={uniqueCounties} selected={countyFilter} onChange={(v) => { setCountyFilter(v); setPage(0); }} />
                    </div>
                  </FilterMenu>
                </SortableTh>
                <SortableTh label="State" sortKey="state" sort={sort} onSort={cycleSort}>
                  <FilterMenu columnKey="state" active={stateFilter.size > 0} {...filterMenuProps}>
                    <div className="w-40 p-2">
                      <CheckboxList options={uniqueStates} selected={stateFilter} onChange={(v) => { setStateFilter(v); setPage(0); }} searchable={false} />
                    </div>
                  </FilterMenu>
                </SortableTh>
                <th className="px-2.5 py-2 font-medium">Coordinates</th>
                {origin && <SortableTh label="Distance" sortKey="distance" sort={sort} onSort={cycleSort} align="right" />}
                <SortableTh label="Rating" sortKey="rating" sort={sort} onSort={cycleSort}>
                  <FilterMenu columnKey="rating" active={Boolean(ratingFilter.min || ratingFilter.max)} {...filterMenuProps}>
                    <NumberRangePanel value={ratingFilter} onChange={(v) => { setRatingFilter(v); setPage(0); }} />
                  </FilterMenu>
                </SortableTh>
                <SortableTh label="Access type" sortKey="access_type" sort={sort} onSort={cycleSort}>
                  <FilterMenu columnKey="access_type" active={accessTypeFilter.size > 0} {...filterMenuProps}>
                    <div className="w-44 p-2">
                      <CheckboxList options={ACCESS_TYPES} selected={accessTypeFilter} onChange={(v) => { setAccessTypeFilter(v); setPage(0); }} searchable={false} />
                    </div>
                  </FilterMenu>
                </SortableTh>
                <SortableTh label="Access company" sortKey="access_company" sort={sort} onSort={cycleSort}>
                  <FilterMenu columnKey="access_company" active={accessCompanyFilter.size > 0} {...filterMenuProps}>
                    <div className="w-56 p-2">
                      <CheckboxList options={uniqueAccessCompanies} selected={accessCompanyFilter} onChange={(v) => { setAccessCompanyFilter(v); setPage(0); }} />
                    </div>
                  </FilterMenu>
                </SortableTh>
                <th className="px-2.5 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {store.loading && (
                <tr><td colSpan={origin ? 9 : 8} className="px-2 py-4 text-center text-[12px] text-muted-foreground">Loading…</td></tr>
              )}
              {!store.loading && pageRows.length === 0 && (
                <tr><td colSpan={origin ? 9 : 8} className="px-2 py-4 text-center text-[12px] text-muted-foreground">No pits found.</td></tr>
              )}
              {pageRows.map((p) => (
                <PitRow key={`${p.latitude},${p.longitude}`} pit={p} store={store} showDistance={Boolean(origin)} />
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
    </div>
  );
}

const inputCls = "w-full rounded-lg border border-black/10 bg-white/70 px-2.5 py-1.5 text-[13px] outline-none focus:border-primary/50";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function PitRow({ pit, store, showDistance }: { pit: PitWithDistance; store: ReturnType<typeof usePitListStore>; showDistance: boolean }) {
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [draft, setDraft] = useState({
    name: pit.name ?? "", county: pit.county ?? "", state: pit.state ?? "",
    rating: pit.rating?.toString() ?? "", access_type: pit.access_type ?? "open",
    access_company: pit.access_company ?? "",
  });
  const [draftCompanyValid, setDraftCompanyValid] = useState(true);

  const save = async () => {
    if (draft.access_company.trim() && !draftCompanyValid) {
      store.setError("Access company must match a name in the competitor registry.");
      return;
    }
    const ok = await store.updatePit(pit.latitude, pit.longitude, {
      name: draft.name || null, county: draft.county || null, state: draft.state || null,
      rating: draft.rating ? Number(draft.rating) : null,
      access_type: draft.access_type || null, access_company: draft.access_company || null,
    });
    if (ok) setEditing(false);
  };

  if (editing) {
    return (
      <tr className="border-b border-black/5">
        <td colSpan={showDistance ? 9 : 8} className="p-2.5">
          <div className="rounded-xl border border-primary/30 bg-white/60 p-2.5">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <Field label="Name">
                <input value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} className={inputCls} />
              </Field>
              <Field label="County">
                <input value={draft.county} onChange={(e) => setDraft((d) => ({ ...d, county: e.target.value }))} className={inputCls} />
              </Field>
              <Field label="State">
                <input value={draft.state} onChange={(e) => setDraft((d) => ({ ...d, state: e.target.value }))} className={inputCls} />
              </Field>
              <Field label="Rating">
                <input value={draft.rating} onChange={(e) => setDraft((d) => ({ ...d, rating: e.target.value }))} inputMode="numeric" className={inputCls} />
              </Field>
              <Field label="Access type">
                <select value={draft.access_type} onChange={(e) => setDraft((d) => ({ ...d, access_type: e.target.value }))} className={inputCls}>
                  {ACCESS_TYPES.map((v) => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
              </Field>
              <Field label="Access company">
                <AccessCompanyPicker
                  value={draft.access_company}
                  onChange={(v) => setDraft((d) => ({ ...d, access_company: v }))}
                  onValidityChange={setDraftCompanyValid}
                />
              </Field>
            </div>
            {store.error && <p className="mt-2 rounded-lg bg-[var(--negative)]/8 px-3 py-2 text-[12px] text-[var(--negative)]">{store.error}</p>}
            <div className="mt-2 flex justify-end gap-2">
              <button onClick={() => setEditing(false)} className="rounded-lg px-2.5 py-1.5 text-[12px] text-muted-foreground hover:text-foreground">Cancel</button>
              <button onClick={save} className="flex items-center gap-1 rounded-lg bg-primary px-2.5 py-1.5 text-[12px] font-medium text-primary-foreground"><Check className="h-3 w-3" /> Save</button>
            </div>
          </div>
        </td>
      </tr>
    );
  }

  return (
    <tr className="border-b border-black/5 hover:bg-black/[0.03]">
      <td className="px-2.5 py-2">
        <div className="flex items-center gap-2">
          <Mountain className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate font-medium">{pit.name || "(unnamed pit)"}</span>
        </div>
      </td>
      <td className="px-2.5 py-2 text-muted-foreground">{pit.county}</td>
      <td className="px-2.5 py-2 text-muted-foreground">{pit.state}</td>
      <td className="px-2.5 py-2">
        <a
          href={mapsLinkFor(pit.latitude, pit.longitude)}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-[11.5px] text-primary hover:underline"
        >
          {pit.latitude}, {pit.longitude}
        </a>
      </td>
      {showDistance && (
        <td className="px-2.5 py-2 text-right font-mono text-[11.5px] text-muted-foreground">
          {pit.distanceMiles != null ? `${pit.distanceMiles.toFixed(1)} mi` : ""}
        </td>
      )}
      <td className="px-2.5 py-2 text-muted-foreground">{pit.rating != null ? `★${pit.rating}` : ""}</td>
      <td className="px-2.5 py-2">
        {pit.access_type && <Chip tone={pit.access_type === "open" ? "positive" : pit.access_type === "closed" ? "negative" : "neutral"}>{pit.access_type}</Chip>}
      </td>
      <td className="px-2.5 py-2 text-muted-foreground">{pit.access_company}</td>
      <td className="px-2.5 py-2">
        <div className="flex items-center gap-2">
          <a
            href={mapsLinkFor(pit.latitude, pit.longitude)}
            target="_blank"
            rel="noreferrer"
            title="View on Google Maps"
            className="text-muted-foreground transition-colors hover:text-primary"
          >
            <MapPin className="h-3.5 w-3.5" />
          </a>
          <button onClick={() => setEditing(true)} className="text-muted-foreground transition-colors hover:text-primary"><Pencil className="h-3.5 w-3.5" /></button>
          {confirmDelete ? (
            <div className="flex items-center gap-1">
              <button
                onClick={() => store.deletePit(pit.latitude, pit.longitude)}
                className="rounded-md bg-[var(--negative)]/15 px-2 py-1 text-[11px] font-medium text-[var(--negative)]"
              >
                Confirm delete
              </button>
              <button
                onClick={() => setConfirmDelete(false)}
                className="flex items-center gap-0.5 rounded-md px-1.5 py-1 text-[11px] font-medium text-muted-foreground hover:text-foreground"
              >
                <X className="h-3 w-3" /> Cancel
              </button>
            </div>
          ) : (
            <button onClick={() => setConfirmDelete(true)} className={cn("text-muted-foreground transition-colors hover:text-[var(--negative)]")}><Trash2 className="h-3.5 w-3.5" /></button>
          )}
        </div>
      </td>
    </tr>
  );
}
