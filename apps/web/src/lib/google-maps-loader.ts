"use client";

import { useEffect, useState } from "react";

// Shared Google Maps JS API loader -- lets multiple components on the same page (or across
// client-side navigations) request the map script without double-injecting it. pit-list/page.tsx
// loads the same script via next/script with id="google-maps-script"; this uses the SAME id so
// whichever mounts first satisfies both. Deliberately not next/script here: next/script's
// dedup-by-id only works within one page's own render tree, and this loader needs to be awaitable
// from an arbitrary number of report-card map instances that don't share a parent.

declare global {
  interface Window {
    google?: any; // eslint-disable-line @typescript-eslint/no-explicit-any -- see pit-map.tsx's identical note
  }
}

const SCRIPT_ID = "google-maps-script";
let loadPromise: Promise<void> | null = null;

export function loadGoogleMaps(apiKey: string): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.google?.maps) return Promise.resolve();
  if (loadPromise) return loadPromise;

  loadPromise = new Promise<void>((resolve, reject) => {
    const existing = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    if (existing) {
      // Another mount (this loader or pit-list's <Script>) already added the tag -- wait for it
      // rather than adding a second one.
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", () => reject(new Error("Google Maps script failed to load")));
      return;
    }
    const script = document.createElement("script");
    script.id = SCRIPT_ID;
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}`;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Google Maps script failed to load"));
    document.head.appendChild(script);
  });
  return loadPromise;
}

// `apiKey` may be "" (unconfigured) -- callers should already be gating on hasKey before
// rendering anything that calls this, same convention pit-list/page.tsx uses (HAS_MAPS_KEY).
export function useGoogleMaps(apiKey: string): boolean {
  const [ready, setReady] = useState(
    () => typeof window !== "undefined" && Boolean(window.google?.maps),
  );
  useEffect(() => {
    if (ready || !apiKey) return;
    let cancelled = false;
    loadGoogleMaps(apiKey)
      .then(() => { if (!cancelled) setReady(true); })
      .catch(() => { /* map just doesn't render -- fail-open, same as every *_live.py backend module */ });
    return () => { cancelled = true; };
  }, [ready, apiKey]);
  return ready;
}
