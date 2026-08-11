"use client";

import { useCallback, useEffect, useRef } from "react";
import { useGoogleMaps } from "@/lib/google-maps-loader";

const GOOGLE_MAPS_API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || "";
const HAS_MAPS_KEY = Boolean(GOOGLE_MAPS_API_KEY);

export type NearbyPit = {
  name: string;
  distance_miles: number;
  quality: number | null;
  latitude: number;
  longitude: number;
};

// Read-only, no filtering/click-to-add -- deliberately lighter than pit-list/pit-map.tsx's PitMap,
// which is built for managing the full pit list, not for a compact card under one competitor
// report. Purpose-built for one thing: when two pits share a name (a real, recurring pattern in
// scratch.mn_pit_list -- see nearest_open_pits()'s docstring), their markers land at visibly
// different coordinates, which a text list can never show.
//
// `selectedIndex` (index into `pits`, controlled by the parent's text-list rows) makes clicking a
// pit's NAME open that exact marker's InfoWindow and pan to it -- without this, a user staring at
// two identically-named "State Pit" rows has no way to tell which marker is which. `onMarkerClick`
// is the reverse direction (clicking a marker tells the parent which list row to highlight), kept
// symmetric for the same reason at near-zero extra cost.
export function PitAccessMap({
  origin, pits, selectedIndex, onMarkerClick,
}: {
  origin: { lat: number; lon: number };
  pits: NearbyPit[];
  selectedIndex?: number | null;
  onMarkerClick?: (index: number) => void;
}) {
  const mapsReady = useGoogleMaps(GOOGLE_MAPS_API_KEY);
  const divRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const infoRef = useRef<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const markersRef = useRef<any[]>([]); // eslint-disable-line @typescript-eslint/no-explicit-any -- index-aligned with `pits`
  // onMarkerClick is read from a ref inside the marker-setup effect so that effect doesn't need to
  // re-run (and rebuild every marker) just because the parent passed a new function reference. The
  // ref is written in its own effect, not inline during render (React now errors on that).
  const onMarkerClickRef = useRef(onMarkerClick);
  useEffect(() => {
    onMarkerClickRef.current = onMarkerClick;
  }, [onMarkerClick]);

  const openPitInfo = useCallback((index: number) => {
    const marker = markersRef.current[index];
    const p = pits[index];
    if (!marker || !p || !mapRef.current || !infoRef.current) return;
    const qualityLine = p.quality != null ? `<br/>quality ${p.quality}` : "";
    infoRef.current.setContent(
      `<div style="font-size:12.5px"><strong>${p.name}</strong><br/>${p.distance_miles.toFixed(1)} mi from site${qualityLine}</div>`,
    );
    infoRef.current.open(mapRef.current, marker);
    mapRef.current.panTo(marker.getPosition());
  }, [pits]);

  // Build the map + markers once per (origin, pit set) change.
  useEffect(() => {
    if (!mapsReady || !divRef.current || !window.google || pits.length === 0) return;
    const google = window.google;

    const map = new google.maps.Map(divRef.current, {
      center: { lat: origin.lat, lng: origin.lon },
      zoom: 10,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: false,
    });
    mapRef.current = map;
    infoRef.current = new google.maps.InfoWindow();
    markersRef.current = [];

    const bounds = new google.maps.LatLngBounds();

    new google.maps.Marker({
      position: { lat: origin.lat, lng: origin.lon },
      map,
      title: "Project site",
      icon: {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 8,
        fillColor: "#2563eb",
        fillOpacity: 1,
        strokeColor: "#ffffff",
        strokeWeight: 2,
      },
    });
    bounds.extend({ lat: origin.lat, lng: origin.lon });

    pits.forEach((p, i) => {
      const marker = new google.maps.Marker({
        position: { lat: p.latitude, lng: p.longitude },
        map,
        title: p.name,
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 7,
          fillColor: "#c2410c",
          fillOpacity: 1,
          strokeColor: "#ffffff",
          strokeWeight: 2,
        },
      });
      marker.addListener("click", () => {
        openPitInfo(i);
        onMarkerClickRef.current?.(i);
      });
      markersRef.current[i] = marker;
      bounds.extend({ lat: p.latitude, lng: p.longitude });
    });

    map.fitBounds(bounds);
    // fitBounds can over-zoom when every marker sits close together (e.g. two same-named pits a
    // few hundred feet apart) -- cap it so a single-cluster case doesn't zoom in past street level.
    const listener = google.maps.event.addListenerOnce(map, "bounds_changed", () => {
      if (map.getZoom() > 14) map.setZoom(14);
    });
    return () => google.maps.event.removeListener(listener);
  }, [mapsReady, origin.lat, origin.lon, pits, openPitInfo]);

  // Selecting a list row (parent-controlled) opens that marker without rebuilding the map.
  useEffect(() => {
    if (selectedIndex == null) return;
    openPitInfo(selectedIndex);
  }, [selectedIndex, openPitInfo]);

  if (!HAS_MAPS_KEY || pits.length === 0) return null;

  return (
    <div
      ref={divRef}
      className="mt-2 h-[220px] w-full overflow-hidden rounded-lg border border-black/[0.06]"
    />
  );
}
