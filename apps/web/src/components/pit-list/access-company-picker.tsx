"use client";

import { useEffect, useMemo, useState } from "react";
import { Command } from "cmdk";
import { AlertCircle, Check } from "lucide-react";
import { cn } from "@/lib/utils";

// Excel-filter-style picker restricted to the competitor name registry (scratch.competitor_name_
// registry, via GET /api/ci-data/competitors) — adapts the NameTypeahead pattern already used on
// the competitor-registry page, but strict: a value that doesn't exactly match a registry
// comp_name is flagged invalid rather than silently accepted, so the form can block submit on it.
export function AccessCompanyPicker({
  value,
  onChange,
  onValidityChange,
  placeholder = "Search competitor name…",
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  onValidityChange?: (valid: boolean) => void;
  placeholder?: string;
  className?: string;
}) {
  const [names, setNames] = useState<string[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    fetch("/api/ci-data/competitors")
      .then((res) => res.json())
      .then((data) => {
        if (data.ok) {
          const unique = Array.from(
            new Set((data.competitors ?? []).map((r: { comp_name: string | null }) => r.comp_name).filter(Boolean)),
          ) as string[];
          setNames(unique.sort((a, b) => a.localeCompare(b)));
        }
      })
      .catch(() => {});
  }, []);

  const isValid = useMemo(() => !value || names.includes(value), [value, names]);

  useEffect(() => {
    onValidityChange?.(Boolean(value) && isValid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, isValid]);

  const filtered = useMemo(
    () => (value ? names.filter((n) => n.toLowerCase().includes(value.toLowerCase())) : names).slice(0, 8),
    [names, value],
  );

  return (
    <div className={cn("relative", className)}>
      <div className="relative">
        <input
          value={value}
          onChange={(e) => { onChange(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          placeholder={placeholder}
          className={cn(
            "w-full rounded-lg border bg-white/70 px-2.5 py-1.5 pr-7 text-[13px] outline-none focus:border-primary/50",
            value && !isValid ? "border-[var(--negative)]/50" : "border-black/10",
          )}
        />
        {value && (
          isValid
            ? <Check className="absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--positive)]" />
            : <AlertCircle className="absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--negative)]" />
        )}
      </div>
      {value && !isValid && (
        <p className="mt-1 text-[11px] text-[var(--negative)]">Not in the competitor registry — pick one below or add it in Competitor Registry first.</p>
      )}
      {open && (
        <Command className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-black/10 bg-white shadow-lg">
          <Command.List className="max-h-40 overflow-auto p-1">
            {filtered.length === 0 && (
              <p className="px-2 py-1.5 text-[12px] text-muted-foreground">No matching competitors.</p>
            )}
            {filtered.map((n) => (
              <Command.Item
                key={n}
                onSelect={() => { onChange(n); setOpen(false); }}
                className="cursor-pointer rounded-md px-2 py-1.5 text-[12px] data-[selected=true]:bg-primary/10"
              >
                {n}
              </Command.Item>
            ))}
          </Command.List>
        </Command>
      )}
    </div>
  );
}
