"use client";

import { useCallback, useState } from "react";

export type Pit = {
  latitude: number;
  longitude: number;
  name: string | null;
  access: string | null;
  county: string | null;
  rating: number | null;
  state: string | null;
  access_type: string | null;
  access_company: string | null;
};

export type PitWithDistance = Pit & { distanceMiles: number | null };

export type PitForm = {
  latitude: string;
  longitude: string;
  name: string;
  access: string;
  county: string;
  rating: string;
  state: string;
  access_type: string;
  access_company: string;
};

export const emptyPitForm = (): PitForm => ({
  latitude: "", longitude: "", name: "", access: "", county: "", rating: "", state: "",
  access_type: "open", access_company: "",
});

const REQUIRED_LABELS: Record<keyof PitForm, string> = {
  latitude: "Latitude", longitude: "Longitude", name: "Name", access: "Access (raw owner text)",
  county: "County", rating: "Rating", state: "State", access_type: "Access type",
  access_company: "Access company",
};

// Every field required on create (the "make all fields required" ask) — checked here so it's not
// duplicated between the form and any other caller of createPit.
export function firstMissingField(form: PitForm): string | null {
  for (const key of Object.keys(REQUIRED_LABELS) as (keyof PitForm)[]) {
    if (!form[key]?.toString().trim()) return `${REQUIRED_LABELS[key]} is required.`;
  }
  return null;
}

type Warning = { warning: string; message: string; existing?: unknown };

function toPayload(f: PitForm) {
  return {
    latitude: Number(f.latitude),
    longitude: Number(f.longitude),
    name: f.name || null,
    access: f.access || null,
    county: f.county || null,
    rating: f.rating ? Number(f.rating) : null,
    state: f.state || null,
    access_type: f.access_type || null,
    access_company: f.access_company || null,
  };
}

export function usePitListStore() {
  const [pits, setPits] = useState<Pit[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<Warning | null>(null);
  const [saving, setSaving] = useState(false);

  const fetchPits = useCallback(async (q?: string) => {
    setLoading(true);
    try {
      const qs = q ? `?search=${encodeURIComponent(q)}` : "";
      const res = await fetch(`/api/ci-data/pits${qs}`);
      const data = await res.json();
      setPits(data.ok ? data.pits ?? [] : []);
      if (!data.ok) setError(data.message ?? "Could not load pits.");
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setLoading(false);
    }
  }, []);

  const createPit = useCallback(async (form: PitForm, force = false): Promise<boolean> => {
    setError(null);
    setWarning(null);
    const missing = firstMissingField(form);
    if (missing) {
      setError(missing);
      return false;
    }
    setSaving(true);
    try {
      const res = await fetch(`/api/ci-data/pits`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...toPayload(form), force }),
      });
      const data = await res.json();
      if (res.status === 409 && data.warning) {
        setWarning(data as Warning);
        return false;
      }
      if (!data.ok) {
        setError(data.message ?? "Could not save the pit.");
        return false;
      }
      await fetchPits();
      return true;
    } catch {
      setError("Could not reach the backend.");
      return false;
    } finally {
      setSaving(false);
    }
  }, [fetchPits]);

  const updatePit = useCallback(async (latitude: number, longitude: number, fields: Record<string, unknown>): Promise<boolean> => {
    setError(null);
    setSaving(true);
    try {
      const res = await fetch(`/api/ci-data/pits/${latitude}/${longitude}`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(fields),
      });
      const data = await res.json();
      if (!data.ok) {
        setError(data.message ?? "Could not update the pit.");
        return false;
      }
      await fetchPits();
      return true;
    } catch {
      setError("Could not reach the backend.");
      return false;
    } finally {
      setSaving(false);
    }
  }, [fetchPits]);

  const deletePit = useCallback(async (latitude: number, longitude: number): Promise<boolean> => {
    setError(null);
    try {
      const res = await fetch(`/api/ci-data/pits/${latitude}/${longitude}`, { method: "DELETE" });
      const data = await res.json();
      if (!data.ok) {
        setError(data.message ?? "Could not delete the pit.");
        return false;
      }
      setPits((prev) => prev.filter((p) => !(p.latitude === latitude && p.longitude === longitude)));
      return true;
    } catch {
      setError("Could not reach the backend.");
      return false;
    }
  }, []);

  return {
    pits, loading, search, setSearch, fetchPits,
    createPit, updatePit, deletePit,
    error, setError, warning, setWarning, saving,
  };
}
