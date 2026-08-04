"use client";

import { useEffect, useRef } from "react";
import { MapPin } from "lucide-react";
import { Glass } from "@/components/kit";
import type { Pit } from "./use-pit-list-store";

// Google Maps JS types aren't installed (no @types/google.maps in package.json, and this repo
// avoids adding deps it doesn't need) — window.google is loaded dynamically by the <Script> tag
// in pit-list/page.tsx, so it's untyped here by necessity, not by neglect.
declare global {
  interface Window {
    google?: any; // eslint-disable-line @typescript-eslint/no-explicit-any
  }
}

const MN_CENTER = { lat: 46.3, lng: -94.3 };

export function PitMap({ pits, mapsReady, hasKey }: { pits: Pit[]; mapsReady: boolean; hasKey: boolean }) {
  const divRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const markersRef = useRef<any[]>([]); // eslint-disable-line @typescript-eslint/no-explicit-any
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

    if (pits.length === 0) return;

    const bounds = new window.google.maps.LatLngBounds();
    for (const pit of pits) {
      const position = { lat: pit.latitude, lng: pit.longitude };
      const marker = new window.google.maps.Marker({ position, map, title: pit.name ?? undefined });
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
    }
    if (pits.length === 1) {
      map.setCenter({ lat: pits[0].latitude, lng: pits[0].longitude });
      map.setZoom(10);
    } else {
      map.fitBounds(bounds);
    }
  }, [mapsReady, pits]);

  if (!hasKey) {
    return (
      <Glass className="flex h-64 flex-col items-center justify-center gap-2 p-4 text-center">
        <MapPin className="h-5 w-5 text-muted-foreground" />
        <p className="text-[12.5px] text-muted-foreground">
          Set <code className="rounded bg-black/5 px-1 py-0.5">NEXT_PUBLIC_GOOGLE_MAPS_API_KEY</code> in
          <code className="rounded bg-black/5 px-1 py-0.5">apps/web/.env.local</code> to enable the map.
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
