"use client";

import { useMemo, useState } from "react";
import { Command } from "cmdk";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";

// Bid-projects search restricted to what this picker needs — a subset of the Project type in
// components/projects/use-projects-store.ts, fetched from the same GET /api/ci-data/projects
// endpoint the Projects page uses.
export type ProjectHit = {
  project_natural_key: string;
  project_name: string | null;
  county: string | null;
  state: string | null;
  bid_date: string | null;
  project_latitude: number | null;
  project_longitude: number | null;
};

// Lazy-loaded, not fetched on pit-list page mount — this is a different table's data, no reason to
// hit it until someone actually opens the "by project" search.
export function ProjectMidpointPicker({
  onSelect,
  placeholder = "Search bid projects…",
}: {
  onSelect: (project: ProjectHit) => void;
  placeholder?: string;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [projects, setProjects] = useState<ProjectHit[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loading, setLoading] = useState(false);

  const ensureLoaded = () => {
    if (loaded || loading) return;
    setLoading(true);
    fetch("/api/ci-data/projects")
      .then((res) => res.json())
      .then((data) => {
        if (data.ok) setProjects(data.projects ?? []);
        setLoaded(true);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return projects
      .filter((p) =>
        `${p.project_name ?? ""} ${p.project_natural_key} ${p.county ?? ""}`.toLowerCase().includes(q),
      )
      .slice(0, 8);
  }, [projects, query]);

  return (
    <div className="relative">
      <div className="flex items-center gap-2 rounded-lg border border-black/10 bg-white/70 px-2.5 py-1.5">
        <Search className="h-3.5 w-3.5 text-muted-foreground" />
        <input
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => { setOpen(true); ensureLoaded(); }}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          placeholder={placeholder}
          className="w-full bg-transparent text-[13px] outline-none placeholder:text-muted-foreground"
        />
      </div>
      {open && query && (
        <Command className="absolute left-0 z-20 mt-1 w-full overflow-hidden rounded-lg border border-black/10 bg-white shadow-lg">
          <Command.List className="max-h-56 overflow-auto p-1">
            {loading && <p className="px-2 py-1.5 text-[12px] text-muted-foreground">Loading projects…</p>}
            {!loading && filtered.length === 0 && (
              <p className="px-2 py-1.5 text-[12px] text-muted-foreground">No matching projects.</p>
            )}
            {filtered.map((p) => {
              const hasCoords = p.project_latitude != null && p.project_longitude != null;
              return (
                <Command.Item
                  key={p.project_natural_key}
                  onSelect={() => {
                    if (!hasCoords) return;
                    onSelect(p);
                    setQuery(p.project_name || p.project_natural_key);
                    setOpen(false);
                  }}
                  className={cn(
                    "flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-[12px]",
                    hasCoords ? "cursor-pointer data-[selected=true]:bg-primary/10" : "cursor-not-allowed opacity-50",
                  )}
                >
                  <span className="truncate">
                    {p.project_name || p.project_natural_key}
                    <span className="text-muted-foreground"> · {p.county ?? "—"}, {p.state ?? "—"}</span>
                  </span>
                  {!hasCoords && <span className="shrink-0 text-[10px] text-muted-foreground">no coords</span>}
                </Command.Item>
              );
            })}
          </Command.List>
        </Command>
      )}
    </div>
  );
}
