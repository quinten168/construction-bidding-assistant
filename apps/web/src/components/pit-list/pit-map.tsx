"use client";

import { useEffect, useRef } from "react";
import { MapPin } from "lucide-react";
import { Glass } from "@/components/kit";
import type { PitWithDistance } from "./use-pit-list-store";

// Google Maps JS types aren't installed (no @types/google.maps in package.json, and this repo
// avoids adding deps it doesn't need) — window.google is loaded dynamically by the <Script> tag
// in pit-list/page.tsx, so it's untyped here by necessity, not by neglect.
declare global {
  interface Window {
    google?: any; // eslint-disable-line @typescript-eslint/no-explicit-any
  }
}

const MN_CENTER = { lat: 46.3, lng: -94.3 };

export type MapOrigin = { lat: number; lon: number; label: string };

export function PitMap({
  pits, mapsReady, hasKey, origin,
}: {
  pits: PitWithDistance[];
  mapsReady: boolean;
  hasKey: boolean;
  origin?: MapOrigin | null;
}) {
  const divRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const markersRef = useRef<any[]>([]); // eslint-disable-line @typescript-eslint/no-explicit-any
  const originMarkerRef = useRef<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const infoRef = useRef<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any

  useEffect(() => {
    if (!mapsReady || !divRef.current || !window.google) return;
    if (!mapRef.current) {
      mapRef.current = new window.google.maps.Map(divRef.current, {
        center: MN_CENTER,
        zoom: 6,
        mapTypeControl: false,
        streetViewControl: false,
      });
      infoRef.current = new window.google.maps.InfoWindow();
    }
    const map = mapRef.current;

    markersRef.current.forEach((m) => m.setMap(null));
    markersRef.current = [];
    if (originMarkerRef.current) {
      originMarkerRef.current.setMap(null);
      originMarkerRef.current = null;
    }

    // Small brand-colored dots instead of Google's default full-size teardrop pin — with pits
    // clustered densely across the state, the default ~41px pins visually merge into a solid mass.
    const markerColor =
      getComputedStyle(document.documentElement).getPropertyValue("--primary").trim() || "#c2410c";
    const pitIcon = {
      path: window.google.maps.SymbolPath.CIRCLE,
      scale: 5,
      fillColor: markerColor,
      fillOpacity: 0.9,
      strokeColor: "#ffffff",
      strokeWeight: 1.5,
    };

    const bounds = new window.google.maps.LatLngBounds();
    let hasBounds = false;

    for (const pit of pits) {
      const position = { lat: pit.latitude, lng: pit.longitude };
      const marker = new window.google.maps.Marker({
        position, map, title: pit.name ?? undefined, icon: pitIcon,
      });
      marker.addListener("click", () => {
        infoRef.current.setContent(
          `<div style="font-size:12.5px;line-height:1.5">
             <strong>${escapeHtml(pit.name || "(unnamed pit)")}</strong><br/>
             ${escapeHtml(pit.county ?? "")}, ${escapeHtml(pit.state ?? "")}<br/>
             ${pit.rating != null ? `★${pit.rating}<br/>` : ""}
             ${pit.access_company ? escapeHtml(pit.access_company) : ""}
           </div>`,
        );
        infoRef.current.open({ map, anchor: marker });
      });
      markersRef.current.push(marker);
      bounds.extend(position);
      hasBounds = true;
    }

    // Distinct diamond marker for a "nearest pits" search origin (a project midpoint or a typed-in
    // coordinate) — visually different from the circular pit dots so it reads as the reference
    // point, not another pit.
    if (origin) {
      const originPosition = { lat: origin.lat, lng: origin.lon };
      originMarkerRef.current = new window.google.maps.Marker({
        position: originPosition,
        map,
        title: origin.label,
        zIndex: 999,
        icon: {
          path: window.google.maps.SymbolPath.CIRCLE,
          scale: 8,
          fillColor: "#2563eb",
          fillOpacity: 1,
          strokeColor: "#ffffff",
          strokeWeight: 2,
        },
      });
      originMarkerRef.current.addListener("click", () => {
        infoRef.current.setContent(
          `<div style="font-size:12.5px;line-height:1.5"><strong>${escapeHtml(origin.label)}</strong></div>`,
        );
        infoRef.current.open({ map, anchor: originMarkerRef.current });
      });
      bounds.extend(originPosition);
      hasBounds = true;
    }

    if (!hasBounds) return;
    if (origin) {
      const nearest = [...pits]
        .filter((p) => p.distanceMiles != null)
        .sort((a, b) => (a.distanceMiles as number) - (b.distanceMiles as number))
        .slice(0, 10);
      const nearBounds = new window.google.maps.LatLngBounds();
      nearBounds.extend({ lat: origin.lat, lng: origin.lon });
      for (const p of nearest) nearBounds.extend({ lat: p.latitude, lng: p.longitude });
      map.fitBounds(nearBounds);
      // fitBounds can zoom to Google's max level when points are tightly clustered (or only the
      // origin is available) — cap it so the view stays at a sensible neighborhood scale.
      window.google.maps.event.addListenerOnce(map, "bounds_changed", () => {
        if (map.getZoom() > 14) map.setZoom(14);
      });
    } else if (pits.length === 1) {
      map.setCenter({ lat: pits[0].latitude, lng: pits[0].longitude });
      map.setZoom(10);
    } else {
      map.fitBounds(bounds);
    }
  }, [mapsReady, pits, origin]);

  if (!hasKey) {
    return (
      <Glass className="flex h-64 flex-col items-center justify-center gap-2 p-4 text-center">
        <MapPin className="h-5 w-5 text-muted-foreground" />
        <p className="text-[12.5px] text-muted-foreground">
          Set <code className="rounded bg-black/5 px-1 py-0.5">NEXT_PUBLIC_GOOGLE_MAPS_API_KEY</code> in
          the repo-root <code className="rounded bg-black/5 px-1 py-0.5">.env</code> to enable the map.
        </p>
      </Glass>
    );
  }

  return (
    <Glass className="overflow-hidden p-0">
      <div ref={divRef} className="h-64 w-full" />
    </Glass>
  );
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
