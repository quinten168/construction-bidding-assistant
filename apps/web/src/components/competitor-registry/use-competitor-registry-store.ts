"use client";

import { useCallback, useState } from "react";

export type RegistryRow = {
  raw_name_variant: string;
  comp_name: string | null;
  source: string | null;
  top_competitors_tag: string | null;
  suggested_comp: string | null;
};

type Warning = { warning: string; message: string; existing?: { comp_name: string; score: number } };

export function useCompetitorRegistryStore() {
  const [rows, setRows] = useState<RegistryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<Warning | null>(null);
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // The full, unfiltered registry — kept separate from `rows` (which tracks the sidebar's own
  // search/needs-review filter) so the add-competitor typeahead can always suggest across every
  // existing raw name variant, regardless of what the user has the main list filtered to.
  const [allRows, setAllRows] = useState<RegistryRow[]>([]);

  const fetchRows = useCallback(async (q?: string, reviewOnly?: boolean) => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (q) params.set("search", q);
      if (reviewOnly) params.set("needs_review_only", "true");
      const res = await fetch(`/api/ci-data/competitors?${params.toString()}`);
      const data = await res.json();
      setRows(data.ok ? data.competitors ?? [] : []);
      if (!data.ok) setError(data.message ?? "Could not load the registry.");
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAllRows = useCallback(async () => {
    try {
      const res = await fetch(`/api/ci-data/competitors`);
      const data = await res.json();
      if (data.ok) setAllRows(data.competitors ?? []);
    } catch {
      // best-effort — a failed refresh just means the typeahead's suggestion list goes stale,
      // not a user-facing error worth surfacing on top of whatever fetchRows already reported
    }
  }, []);

  const addCompetitor = useCallback(async (name: string, tag: string, force = false): Promise<boolean> => {
    setError(null);
    setWarning(null);
    if (!name.trim()) {
      setError("A competitor name is required.");
      return false;
    }
    setSaving(true);
    try {
      const res = await fetch(`/api/ci-data/competitors`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: name.trim(), top_competitors_tag: tag || null, force }),
      });
      const data = await res.json();
      if (res.status === 409 && data.warning) {
        setWarning(data as Warning);
        return false;
      }
      if (!data.ok) {
        setError(data.message ?? "Could not add competitor.");
        return false;
      }
      await Promise.all([fetchRows(search, needsReviewOnly), fetchAllRows()]);
      return true;
    } catch {
      setError("Could not reach the backend.");
      return false;
    } finally {
      setSaving(false);
    }
  }, [fetchRows, fetchAllRows, search, needsReviewOnly]);

  const toggleSelected = useCallback((rawName: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(rawName)) next.delete(rawName);
      else next.add(rawName);
      return next;
    });
  }, []);

  const clearSelected = useCallback(() => setSelected(new Set()), []);

  const consolidate = useCallback(async (targetCompName: string): Promise<boolean> => {
    setError(null);
    if (selected.size === 0) {
      setError("Select at least one name to consolidate.");
      return false;
    }
    if (!targetCompName.trim()) {
      setError("A target competitor name is required.");
      return false;
    }
    setSaving(true);
    try {
      const res = await fetch(`/api/ci-data/competitors/consolidate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ raw_name_variants: Array.from(selected), target_comp_name: targetCompName.trim() }),
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.message ?? "Could not consolidate.");
        return false;
      }
      clearSelected();
      await Promise.all([fetchRows(search, needsReviewOnly), fetchAllRows()]);
      return true;
    } catch {
      setError("Could not reach the backend.");
      return false;
    } finally {
      setSaving(false);
    }
  }, [selected, clearSelected, fetchRows, fetchAllRows, search, needsReviewOnly]);

  const removeCompetitor = useCallback(async (compName: string): Promise<boolean> => {
    setError(null);
    try {
      const res = await fetch(`/api/ci-data/competitors/${encodeURIComponent(compName)}`, { method: "DELETE" });
      const data = await res.json();
      if (!data.ok) {
        setError(data.message ?? "Could not remove competitor.");
        return false;
      }
      await Promise.all([fetchRows(search, needsReviewOnly), fetchAllRows()]);
      return true;
    } catch {
      setError("Could not reach the backend.");
      return false;
    }
  }, [fetchRows, fetchAllRows, search, needsReviewOnly]);

  const removeRawNameVariant = useCallback(async (rawName: string): Promise<boolean> => {
    setError(null);
    try {
      const res = await fetch(`/api/ci-data/competitor-raw-names/${encodeURIComponent(rawName)}`, { method: "DELETE" });
      const data = await res.json();
      if (!data.ok) {
        setError(data.message ?? "Could not remove that name.");
        return false;
      }
      await Promise.all([fetchRows(search, needsReviewOnly), fetchAllRows()]);
      return true;
    } catch {
      setError("Could not reach the backend.");
      return false;
    }
  }, [fetchRows, fetchAllRows, search, needsReviewOnly]);

  return {
    rows, loading, search, setSearch, needsReviewOnly, setNeedsReviewOnly, fetchRows,
    allRows, fetchAllRows,
    addCompetitor, error, warning, setWarning, saving,
    selected, toggleSelected, clearSelected, consolidate, removeCompetitor, removeRawNameVariant,
  };
}
