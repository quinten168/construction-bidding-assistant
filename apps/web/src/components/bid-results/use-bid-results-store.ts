"use client";

import { useCallback, useState } from "react";

export type MissingResultsProject = {
  project_natural_key: string;
  project_name: string | null;
  county: string | null;
  state: string | null;
  bid_date: string | null;
  bid_year: number | null;
};

export type BidEntryForm = {
  raw_bidder_name: string;
  bid_amount: string; // kept as string while editing, parsed to float on submit
};

export const emptyEntry = (): BidEntryForm => ({ raw_bidder_name: "", bid_amount: "" });

type SubmitResult = { ok: true; project_natural_key: string; entries_saved: number }
  | { ok: false; message: string };

// One row per bidder per project — mirrors scratch.bid_results joined to scratch.bid_projects,
// the grain the full results table (as opposed to the missing-results picker above) reads at.
export type BidResultRow = {
  project_natural_key: string;
  competitor_unit_id: string;
  raw_bidder_name: string;
  bid_amount: number;
  bid_rank: number | null;
  did_win: boolean;
  mapping_status: string | null;
  // Presentation-only, resolved live through the name registry — differs from raw_bidder_name only
  // when this row's competitor has since been consolidated onto a new canonical name.
  current_comp_name: string;
  project_name: string | null;
  county: string | null;
  state: string | null;
  bid_date: string | null;
  bid_year: number | null;
};

type BidResultEditableFields = Partial<Pick<BidResultRow, "raw_bidder_name" | "bid_amount">>;

type UpdateResult = { ok: true; project_natural_key: string; rows: BidResultRow[] } | { ok: false; message: string };

export function useBidResultsStore() {
  const [projects, setProjects] = useState<MissingResultsProject[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<MissingResultsProject | null>(null);
  const [entries, setEntries] = useState<BidEntryForm[]>([emptyEntry(), emptyEntry()]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSaved, setLastSaved] = useState<string | null>(null);

  const [results, setResults] = useState<BidResultRow[]>([]);
  const [loadingResults, setLoadingResults] = useState(false);
  const [resultsSearch, setResultsSearch] = useState("");
  const [resultsError, setResultsError] = useState<string | null>(null);

  const fetchProjects = useCallback(async (q?: string) => {
    setLoadingProjects(true);
    try {
      const qs = q ? `?search=${encodeURIComponent(q)}` : "";
      const res = await fetch(`/api/ci-data/projects/missing-results${qs}`);
      const data = await res.json();
      setProjects(data.ok ? data.projects ?? [] : []);
      if (!data.ok) setError(data.message ?? "Could not load projects.");
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setLoadingProjects(false);
    }
  }, []);

  const selectProject = useCallback((p: MissingResultsProject | null) => {
    setSelected(p);
    setEntries([emptyEntry(), emptyEntry()]);
    setError(null);
    setLastSaved(null);
  }, []);

  const updateEntry = useCallback((i: number, patch: Partial<BidEntryForm>) => {
    setEntries((prev) => prev.map((e, idx) => (idx === i ? { ...e, ...patch } : e)));
  }, []);

  const addRow = useCallback(() => {
    setEntries((prev) => [...prev, emptyEntry()]);
  }, []);

  const removeRow = useCallback((i: number) => {
    setEntries((prev) => (prev.length <= 1 ? prev : prev.filter((_, idx) => idx !== i)));
  }, []);

  const submit = useCallback(async (): Promise<boolean> => {
    if (!selected) return false;
    setError(null);

    const filled = entries.filter((e) => e.raw_bidder_name.trim() || e.bid_amount.trim());
    if (filled.length === 0) {
      setError("Enter at least one bidder.");
      return false;
    }
    if (filled.some((e) => !e.raw_bidder_name.trim() || !e.bid_amount.trim())) {
      setError("Every row needs both a bidder name and a bid amount.");
      return false;
    }

    setSubmitting(true);
    try {
      const res = await fetch(`/api/ci-data/projects/${encodeURIComponent(selected.project_natural_key)}/bid-results`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          entries: filled.map((e) => ({
            raw_bidder_name: e.raw_bidder_name.trim(),
            bid_amount: Number(e.bid_amount),
          })),
        }),
      });
      const data: SubmitResult = await res.json();
      if (!data.ok) {
        setError(data.message ?? "Could not save bid results.");
        return false;
      }
      setLastSaved(selected.project_natural_key);
      setProjects((prev) => prev.filter((p) => p.project_natural_key !== selected.project_natural_key));
      setSelected(null);
      setEntries([emptyEntry(), emptyEntry()]);
      return true;
    } catch {
      setError("Could not reach the backend.");
      return false;
    } finally {
      setSubmitting(false);
    }
  }, [selected, entries]);

  const fetchResults = useCallback(async (q?: string) => {
    setLoadingResults(true);
    try {
      const qs = q ? `?search=${encodeURIComponent(q)}` : "";
      const res = await fetch(`/api/ci-data/bid-results${qs}`);
      const data = await res.json();
      setResults(data.ok ? data.results ?? [] : []);
      if (!data.ok) setResultsError(data.message ?? "Could not load bid results.");
    } catch {
      setResultsError("Could not reach the backend.");
    } finally {
      setLoadingResults(false);
    }
  }, []);

  // Patches just the edited project's rows in place (a project-scoped response, not the whole
  // table) so a cell edit doesn't cause a full-table refetch/scroll-jump on every keystroke-blur.
  const updateResult = useCallback(async (
    projectNaturalKey: string,
    competitorUnitId: string,
    patch: BidResultEditableFields,
  ): Promise<boolean> => {
    setResultsError(null);
    try {
      const res = await fetch(
        `/api/ci-data/bid-results/${encodeURIComponent(projectNaturalKey)}/${encodeURIComponent(competitorUnitId)}`,
        { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify(patch) },
      );
      const data: UpdateResult = await res.json();
      if (!data.ok) {
        setResultsError(data.message ?? "Could not save the edit.");
        return false;
      }
      setResults((prev) => {
        const idx = prev.findIndex((r) => r.project_natural_key === projectNaturalKey);
        const rest = prev.filter((r) => r.project_natural_key !== projectNaturalKey);
        if (idx === -1) return [...rest, ...data.rows];
        return [...rest.slice(0, idx), ...data.rows, ...rest.slice(idx)];
      });
      return true;
    } catch {
      setResultsError("Could not reach the backend.");
      return false;
    }
  }, []);

  return {
    projects, loadingProjects, search, setSearch, fetchProjects,
    selected, selectProject, entries, updateEntry, addRow, removeRow,
    submit, submitting, error, lastSaved,
    results, loadingResults, resultsSearch, setResultsSearch, fetchResults, updateResult, resultsError,
  };
}
