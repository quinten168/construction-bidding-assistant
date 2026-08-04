"use client";

import { useCallback, useState } from "react";

// One row per historical letting — mirrors scratch.bid_projects. Only the seven material-quantity
// fields are editable from this page; everything else here is read-only display.
export type Project = {
  project_natural_key: string;
  source_project_id: string | null;
  bid_date: string | null;
  bid_year: number | null;
  state: string | null;
  county: string | null;
  project_location: string | null;
  project_name: string | null;
  project_latitude: number | null;
  project_longitude: number | null;
  mix_tons: number | null;
  grading_yards: number | null;
  base_tons: number | null;
  shldr_tons: number | null;
  mill_sy: number | null;
  crush_tons: number | null;
  stock_tons: number | null;
  project_type: string | null;
};

export const MATERIAL_FIELDS = [
  "mix_tons", "grading_yards", "base_tons", "shldr_tons", "mill_sy", "crush_tons", "stock_tons",
] as const;

export type MaterialField = (typeof MATERIAL_FIELDS)[number];

type UpdateResult = { ok: true; project: Project } | { ok: false; message: string };

export function useProjectsStore() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  const fetchProjects = useCallback(async (q?: string) => {
    setLoading(true);
    try {
      const qs = q ? `?search=${encodeURIComponent(q)}` : "";
      const res = await fetch(`/api/ci-data/projects${qs}`);
      const data = await res.json();
      setProjects(data.ok ? data.projects ?? [] : []);
      if (!data.ok) setError(data.message ?? "Could not load projects.");
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setLoading(false);
    }
  }, []);

  const updateMaterials = useCallback(async (
    projectNaturalKey: string,
    patch: Partial<Record<MaterialField, number | null>>,
  ): Promise<boolean> => {
    setError(null);
    try {
      const res = await fetch(`/api/ci-data/projects/${encodeURIComponent(projectNaturalKey)}/materials`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(patch),
      });
      const data: UpdateResult = await res.json();
      if (!data.ok) {
        setError(data.message ?? "Could not save the edit.");
        return false;
      }
      setProjects((prev) => prev.map((p) => (p.project_natural_key === projectNaturalKey ? data.project : p)));
      return true;
    } catch {
      setError("Could not reach the backend.");
      return false;
    }
  }, []);

  return { projects, loading, search, setSearch, fetchProjects, updateMaterials, error };
}
