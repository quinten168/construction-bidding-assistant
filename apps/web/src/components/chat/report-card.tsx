"use client";

import { useState } from "react";
import { motion } from "motion/react";
import { Check, ChevronDown, Copy, Download, FileText, Users } from "lucide-react";
import { type FinalReport, type FinalGotcha, type Competitor, type CompetitorStats, type ScopedRate } from "@/lib/chat-data";
import { Eyebrow, Chip } from "@/components/kit";

// ────────────────────────────────────────────────────────────────────────────
// The signature artifact: a readable plan REPORT CARD rendered INLINE in the
// conversation right after the processing narration. Built from the REAL
// assembled report (FastAPI /api/report → final), not the mock. Every figure is
// pinned to its source page. (Visual redesign is a later phase — this renders the
// real data faithfully.)
// ────────────────────────────────────────────────────────────────────────────

// Identity fields we surface, in display order, with friendly labels.
// Order (client request): State (full) → County → Project no. → Location, then the rest.
const IDENTITY_LABELS: [string, string][] = [
  ["state", "State"],
  ["county", "County"],
  ["sp_number", "Project no."],
  ["location", "Location"],
  ["traffic_level", "Traffic level"],
  ["construction_start", "Construction start"],
];

// Two-letter DOT state code → full name (we surface the full state, not the abbreviation).
const STATE_NAMES: Record<string, string> = {
  ND: "North Dakota", MN: "Minnesota", SD: "South Dakota", MT: "Montana", IA: "Iowa", WI: "Wisconsin",
};

function fmtVal(v: string | number | boolean | null): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  return String(v);
}

// A clean "County County, ST" place label from the identity (skips empty parts).
function placeLabel(identity: Record<string, string | number | boolean | null>): string {
  const county = fmtVal(identity.county ?? null);
  const state = fmtVal(identity.state ?? null);
  const parts: string[] = [];
  if (county !== "—") parts.push(`${county} County`);
  if (state !== "—") parts.push(String(state));
  return parts.join(", ");
}

// Per-field display formatting. A plan can bundle several SAP/contract numbers — show the
// first and collapse the rest ("SAP 012-604-021 +4 more") instead of a wall of numbers.
function fmtIdentity(key: string, v: string | number | boolean | null): string {
  const s = fmtVal(v);
  if (key === "state" && s !== "—") return STATE_NAMES[s.toUpperCase()] ?? s;
  if (key === "sp_number" && s !== "—") {
    const parts = s.split(",").map((p) => p.trim()).filter(Boolean);
    if (parts.length > 1) return `${parts[0]} +${parts.length - 1} more`;
  }
  return s;
}

// Taxonomy codes (PHASING_SEQUENCED) → a readable title ("Phasing Sequenced").
function humanize(code: string): string {
  return code
    .toLowerCase()
    .split(/[_\s]+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function reportToMarkdown(f: FinalReport): string {
  const lines = [`# ${f.title}`, "", `**Archetype:** ${f.archetype}`, "", f.tldr, ""];
  lines.push("## Identity");
  for (const [k, label] of IDENTITY_LABELS) {
    if (f.identity[k] != null && f.identity[k] !== "") lines.push(`- **${label}:** ${fmtVal(f.identity[k])}`);
  }
  if (f.quantities.length) {
    lines.push("", "## Quantities");
    for (const q of f.quantities) lines.push(`- ${q.label}: ${q.value} ${q.unit}`);
  }
  const all = [...f.gotchas.go_no_go, ...f.gotchas.pricing];
  if (all.length) {
    lines.push("", "## Gotchas");
    for (const g of all) lines.push(`- [${g.family ?? "flag"}] ${g.code} (p.${g.page ?? "?"}) — "${g.evidence ?? ""}"`);
  }
  return lines.join("\n");
}

// POST the assembled report to the export proxy and trigger a browser download of the returned
// file. Returns an error string on failure (the caller surfaces it) or null on success.
async function downloadReport(final: FinalReport, fmt: "md" | "csv" | "pdf"): Promise<string | null> {
  let res: Response;
  try {
    res = await fetch("/api/report/export", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ final, fmt }),
    });
  } catch {
    return "Couldn't reach the export service.";
  }
  if (!res.ok) {
    let msg = `Export failed (${res.status}).`;
    try {
      const j = await res.json();
      if (j?.message) msg = j.message;
    } catch {
      /* not JSON — keep the status message */
    }
    return msg;
  }
  const blob = await res.blob();
  if (!blob.size) return "The export came back empty.";
  // honor the filename the backend set in Content-Disposition; fall back to a sane stem
  const cd = res.headers.get("content-disposition") ?? "";
  const m = cd.match(/filename="?([^"]+)"?/);
  const name = m?.[1] ?? `bid-report.${fmt}`;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.rel = "noopener";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  // Defer cleanup — revoking the object URL synchronously right after click() cancels the
  // download in Chrome/Safari before it starts reading the blob (the "button does nothing" bug).
  setTimeout(() => {
    a.remove();
    URL.revokeObjectURL(url);
  }, 2000);
  return null;
}

export function ReportCard({ final }: { final?: FinalReport }) {
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [dlError, setDlError] = useState<string | null>(null);

  if (!final) {
    return (
      <div className="glass-strong rounded-2xl border border-black/[0.06] px-4 py-3 text-[13px] text-muted-foreground">
        Report data unavailable — re-drop the plan PDF.
      </div>
    );
  }

  const copy = () => {
    navigator.clipboard?.writeText(reportToMarkdown(final));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const goNoGo = final.gotchas.go_no_go ?? [];
  const pricing = final.gotchas.pricing ?? [];
  const allGotchas: FinalGotcha[] = [...goNoGo, ...pricing];
  const identityRows = IDENTITY_LABELS.filter(([k]) => final.identity[k] != null && final.identity[k] !== "");

  const bidDate = final.competitor?.bid_date || null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 200, damping: 26 }}
      className="overflow-hidden rounded-2xl border border-black/[0.08] bg-white elev-md"
    >
      {/* Masthead — reads as a report cover, not a chat bubble */}
      <div className="border-b-2 border-primary/25 px-7 pt-7 pb-5">
        <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-primary">
          <FileText className="h-3.5 w-3.5" /> Bid Intelligence Report
        </div>
        <h3 className="mt-2.5 font-serif text-[32px] leading-[1.08] tracking-tight">{final.title}</h3>
        <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[14px] text-muted-foreground">
          <span className="font-medium text-foreground/75">{final.archetype}</span>
          {final.pages ? <><span className="text-muted-foreground/40">·</span><span>{final.pages} pp</span></> : null}
          {allGotchas.length > 0 && <><span className="text-muted-foreground/40">·</span><span>{allGotchas.length} gotchas</span></>}
          {bidDate && <><span className="text-muted-foreground/40">·</span><span>Bid {bidDate}</span></>}
        </p>
      </div>

      {/* Body */}
      <div className="space-y-7 px-7 py-6">
        {/* Headline summary — scannable "what is this" BEFORE the detail: bold work-type + place,
            then counts + top watch-item as pills (a paragraph here was hard to read). */}
        <Headline
          archetype={final.archetype}
          place={placeLabel(final.identity)}
          goNoGo={goNoGo.length}
          pricing={pricing.length}
          wage={final.identity.prevailing_wages === true}
          watch={goNoGo[0] ? humanize(goNoGo[0].code) : pricing[0] ? humanize(pricing[0].code) : null}
        />

        {/* ① Snapshot — dates strip + project identity, merged (all quick-scan facts in one place) */}
        <section>
          <SectionHeader n={1} title="Snapshot" />
          {/* Dates lead — Adam checks bid deadline + completion first, and they're scattered/hard to find */}
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Snapshot label="Bid deadline" value={fmtVal(final.identity.bid_deadline)} accent />
            <Snapshot label="Substantial completion" value={fmtVal(final.identity.substantial_completion ?? final.identity.construction_end)} />
            <Snapshot label="Final completion" value={fmtVal(final.identity.final_completion)} />
            <Snapshot label="Prevailing wage" value={fmtVal(final.identity.prevailing_wages)} />
          </div>
          {identityRows.length > 0 && (
            <dl className="mt-4 grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2">
              {identityRows.map(([k, label]) => (
                <div key={k} className="flex items-baseline justify-between gap-3 border-b border-black/[0.04] py-1.5">
                  <dt className="shrink-0 text-[13px] text-muted-foreground">{label}</dt>
                  <dd className="line-clamp-2 text-right text-[15px] font-medium" title={fmtVal(final.identity[k])}>
                    {fmtIdentity(k, final.identity[k])}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </section>

        {/* ② Headline quantities */}
        {final.quantities.length > 0 && (
          <section>
            <SectionHeader n={2} title="Materials & quantities" aside="bid schedule" />
            <div className="overflow-hidden rounded-xl border border-black/[0.08]">
              <table className="w-full text-[15px]">
                <thead className="bg-secondary/50">
                  <tr>
                    <th className="px-4 py-2.5 text-left text-[12px] font-medium uppercase tracking-wide text-muted-foreground">Item</th>
                    <th className="px-4 py-2.5 text-right text-[12px] font-medium uppercase tracking-wide text-muted-foreground">Quantity</th>
                    <th className="px-4 py-2.5 text-left text-[12px] font-medium uppercase tracking-wide text-muted-foreground">Unit</th>
                  </tr>
                </thead>
                <tbody>
                  {final.quantities.map((q, i) => (
                    <tr key={`${q.label}-${i}`} className="border-t border-black/[0.05] odd:bg-black/[0.015]">
                      <td className="px-4 py-2.5 font-medium">{q.label}</td>
                      <td className="px-4 py-2.5 text-right font-mono tnum">
                        {typeof q.value === "number" ? q.value.toLocaleString() : q.value}
                      </td>
                      <td className="px-4 py-2.5 text-[14px] text-muted-foreground">{q.unit}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* ④ Gotchas — ALL flagged types, split Go/No-Go vs Pricing, each with verbatim evidence + page */}
        {allGotchas.length > 0 && (
          <section>
            <SectionHeader n={3} title="Gotchas" aside={`${allGotchas.length} flagged`} />
            <div className="space-y-4">
              {goNoGo.length > 0 && (
                <GotchaGroup title="Go / No-Go" hint="bid-or-pass risk" tone="warn" items={goNoGo} />
              )}
              {pricing.length > 0 && (
                <GotchaGroup title="Pricing" hint="affects how you price" tone="primary" items={pricing} />
              )}
            </div>
          </section>
        )}

        {/* ⑤ Competitive landscape — the matched / live-generated Competitor Intel report */}
        <section>
          <SectionHeader n={4} title="Competitive landscape" />
          {final.competitor ? (
            <CompetitorSection comp={final.competitor} />
          ) : (
            <p className="rounded-xl border border-black/[0.06] bg-secondary/30 px-3 py-2.5 text-[12px] text-muted-foreground">
              No competitor-intel report matched this project (by county + state + date).
            </p>
          )}
        </section>

        {/* Footer — a quick "what I did" recap + the downloads (they live here, not up top) */}
        <div className="border-t border-black/[0.07] pt-4">
          <p className="text-[13.5px] leading-relaxed text-muted-foreground">
            Read {final.pages ? `${final.pages} pages` : "the plan"} end to end · pinned every figure to its source page ·
            extracted {final.quantities.length} bid-schedule item{final.quantities.length === 1 ? "" : "s"} and flagged {allGotchas.length} gotcha{allGotchas.length === 1 ? "" : "s"}.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-[12px] font-medium text-foreground/70">Download</span>
            {(["pdf", "csv", "md"] as const).map((fmt) => (
              <button
                key={fmt}
                onClick={async () => {
                  setBusy(fmt);
                  setDlError(null);
                  try {
                    const err = await downloadReport(final, fmt);
                    if (err) setDlError(err);
                  } finally {
                    setBusy(null);
                  }
                }}
                disabled={busy !== null}
                title={`Download report as ${fmt.toUpperCase()}`}
                className="flex items-center gap-1 rounded-lg border border-black/10 px-2.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary/30 hover:text-primary disabled:opacity-50"
              >
                <Download className="h-3 w-3" />
                {busy === fmt ? "…" : fmt.toUpperCase()}
              </button>
            ))}
            <button
              onClick={copy}
              title="Copy report as Markdown"
              className="ml-1 flex items-center gap-1 rounded-lg border border-black/10 px-2.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary/30 hover:text-primary"
            >
              {copied ? <Check className="h-3 w-3 text-[var(--positive)]" /> : <Copy className="h-3 w-3" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          {dlError && (
            <p className="mt-2 text-[12px] text-[var(--negative)]">{dlError} — try again or use Copy.</p>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// A numbered report section header with a divider — gives the card its "document" feel.
function SectionHeader({ n, title, aside }: { n: number; title: string; aside?: React.ReactNode }) {
  return (
    <div className="mb-3.5 flex items-center gap-2.5 border-b border-black/[0.07] pb-2">
      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-primary/10 font-serif text-[13px] font-semibold text-primary">
        {n}
      </span>
      <h4 className="font-serif text-[19px] tracking-tight">{title}</h4>
      {aside && <span className="ml-auto text-[11px] uppercase tracking-wide text-muted-foreground">{aside}</span>}
    </div>
  );
}

// The scannable headline summary — bold work-type + place, then counts + watch-item as pills.
function Headline({
  archetype,
  place,
  goNoGo,
  pricing,
  wage,
  watch,
}: {
  archetype: string;
  place: string;
  goNoGo: number;
  pricing: number;
  wage: boolean;
  watch: string | null;
}) {
  return (
    <div className="rounded-2xl border border-primary/20 bg-primary/[0.05] px-5 py-4">
      <p className="text-[18px] font-semibold leading-snug tracking-tight text-foreground">
        {archetype}
        {place && <span className="font-normal text-muted-foreground"> · {place}</span>}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Chip tone={goNoGo > 0 ? "warn" : "neutral"} className="px-2.5 py-1 text-[12px]">{goNoGo} go / no-go</Chip>
        <Chip tone={pricing > 0 ? "primary" : "neutral"} className="px-2.5 py-1 text-[12px]">{pricing} pricing</Chip>
        {wage && <Chip tone="neutral" className="px-2.5 py-1 text-[12px]">Prevailing wage</Chip>}
      </div>
      {watch && (
        <p className="mt-2.5 text-[13.5px] text-muted-foreground">
          Top watch-item: <span className="font-medium text-foreground">{watch}</span>
        </p>
      )}
    </div>
  );
}

// A single quick-scan fact in the snapshot strip. `accent` highlights a key figure (e.g. completion date).
function Snapshot({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`rounded-xl border px-3.5 py-2.5 ${accent ? "border-primary/25 bg-primary/[0.05]" : "border-black/[0.06] bg-card/60"}`}>
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 truncate text-[16px] font-medium" title={value}>{value}</div>
    </div>
  );
}

// A labeled group of gotchas (Go/No-Go or Pricing) — shows ALL flagged types, each with its
// humanized name, verbatim evidence, and source page.
function GotchaGroup({
  title,
  hint,
  tone,
  items,
}: {
  title: string;
  hint: string;
  tone: "warn" | "primary";
  items: FinalGotcha[];
}) {
  const accent = tone === "warn" ? "var(--warn)" : "var(--primary)";
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <Eyebrow>{title}</Eyebrow>
        <span className="text-[10px] text-muted-foreground">{items.length} · {hint}</span>
      </div>
      <div className="mt-2 space-y-1.5">
        {items.map((g, i) => (
          <div
            key={`${g.code}-${i}`}
            className="rounded-xl border border-black/[0.06] bg-card/70 p-3"
            style={{ borderLeft: `3px solid ${accent}` }}
          >
            <div className="flex items-center gap-2">
              <span className="text-[15px] font-medium">{humanize(g.code)}</span>
              {g.page != null && (
                <span className="ml-auto shrink-0 font-mono text-[11px] text-muted-foreground/70">p.{g.page}</span>
              )}
            </div>
            {g.evidence && (
              <p className="mt-1.5 line-clamp-3 text-[13px] italic leading-snug text-muted-foreground" title={g.evidence}>
                &ldquo;{g.evidence}&rdquo;
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Competitive landscape (§④) — CI team's v3 schema ────────────────────────
// A single flat top-N ranking (no Priority/Discovery tiers — CSI's tracked-list membership never
// drove the ranking, only a display grouping that's now gone). Each competitor expands to its
// structured attributes (Bid Rate, Recency, Capacity, Experience, Win Rates). No invented scores
// — their model dropped numeric threat.
const MATCH_TONE: Record<string, string> = { high: "positive", medium: "neutral", low: "warn" };
// the two most decision-relevant attributes to surface inline (rest live in the expand)
const KEY_ATTRS = ["Bid Rate", "Recency"];

function CompetitorSection({ comp }: { comp: Competitor }) {
  const s = comp.summary ?? { analyzed: 0, narrative: "" };
  const conf = (comp._match?.confidence ?? "").toLowerCase();
  const matchTone = MATCH_TONE[conf] ?? "neutral";
  const names = comp.competitors ?? [];
  const userAddedSet = new Set(comp.user_added ?? []);

  return (
    <div>
      {/* Summary panel — the important at-a-glance CI info, given real weight */}
      <div className="rounded-2xl border border-black/[0.08] bg-secondary/30 p-4">
        <div className="flex items-center gap-2 text-[15px] font-medium text-foreground">
          <Users className="h-[18px] w-[18px] text-primary" />
          Top {s.analyzed} likely competitors
        </div>

        {/* match-confidence — a wrong county+date match is visible, not hidden */}
        {conf && (
          <div className="mt-3 flex flex-wrap items-center gap-2 text-[13px]">
            <Chip tone={matchTone as "positive" | "neutral" | "warn"}>
              match: {conf}{comp._match?.basis ? ` · ${comp._match.basis}` : ""}
            </Chip>
          </div>
        )}
        {conf === "low" && (
          <p className="mt-2.5 rounded-lg border border-[var(--warn)]/30 bg-[var(--warn)]/[0.06] px-3 py-2 text-[12.5px] text-foreground/75">
            Low-confidence match (state only) — confirm this competitor set is the same project before relying on it.
          </p>
        )}

        {(comp.work_type || comp.condition) && (
          <p className="mt-3 text-[13.5px] font-medium text-foreground/80">
            {comp.work_type}
            {comp.condition ? ` · ${comp.condition}` : ""}
          </p>
        )}
        {comp.pits?.public && (
          <p className="mt-1.5 text-[12.5px] text-muted-foreground">Pit access: {comp.pits.public}</p>
        )}
      </div>

      {/* Ranked list — best match first. Estimator-added names (typed in via the verify-competitors
          popup) get the same live win_rate/bid_rate/capacity/pit_access retrieval as everyone else,
          just a "you added" badge to distinguish them from the model's own picks. */}
      {names.length > 0 && (
        <div className="mt-2.5 space-y-1.5">
          {names.map((name) => (
            <CompetitorRow
              key={name}
              name={name}
              attrs={comp.attrs?.[name] ?? {}}
              stats={comp.stats?.[name]}
              accent={userAddedSet.has(name) ? "var(--primary)" : "var(--muted-foreground)"}
              isUserAdded={userAddedSet.has(name)}
            />
          ))}
        </div>
      )}

      <p className="mt-2 text-[10px] text-muted-foreground/70">
        Source: {comp.source_file} · Competitor Intelligence model
      </p>
    </div>
  );
}

// One competitor: name + two key attributes inline, expandable to the full attribute set +
// the live-retrieved win/bid rate, capacity, and pit-access figures (same regardless of origin).
function CompetitorRow({
  name, attrs, stats, accent, isUserAdded,
}: {
  name: string;
  attrs: Record<string, string>;
  stats?: CompetitorStats;
  accent: string;
  isUserAdded?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const keys = Object.keys(attrs);
  const inline = KEY_ATTRS.map((k) => attrs[k]).filter(Boolean);
  const expandable = keys.length > 0 || Boolean(stats);

  return (
    <div className="rounded-xl border border-black/[0.06] bg-card/70 p-2.5" style={{ borderLeft: `3px solid ${accent}` }}>
      <button
        onClick={() => expandable && setOpen((v) => !v)}
        className="flex w-full items-center gap-2 text-left"
        disabled={!expandable}
      >
        <span className="text-[14px] font-medium">{name}</span>
        {isUserAdded && <Chip tone="primary">you added</Chip>}
        {expandable && (
          <ChevronDown className={`ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
        )}
      </button>
      {inline.length > 0 && !open && (
        <p className="mt-1 line-clamp-1 text-[12.5px] text-muted-foreground" title={inline.join(" · ")}>
          {inline.join(" · ")}
        </p>
      )}
      {open && keys.length > 0 && (
        <dl className="mt-1.5 space-y-1">
          {keys.map((k) => (
            <div key={k} className="text-[11.5px] leading-snug">
              <dt className="font-medium text-foreground/70">{k}</dt>
              <dd className="text-muted-foreground">{attrs[k]}</dd>
            </div>
          ))}
        </dl>
      )}
      {open && <CompetitorStatsBlock stats={stats} />}
    </div>
  );
}

function fmtPct(pct: number | null | undefined): string {
  return pct == null ? "—" : `${Math.round(pct * 100)}%`;
}

function fmtScoped(r?: ScopedRate): string {
  if (!r) return "—";
  const raw = r.wins != null && r.bids != null ? `${r.wins}/${r.bids}` : r.bids != null && r.total != null ? `${r.bids}/${r.total}` : null;
  return raw ? `${raw} · ${fmtPct(r.pct)}` : fmtPct(r.pct);
}

function fmtTons(t: number | null | undefined): string {
  return t == null ? "—" : `${Math.round(t).toLocaleString()} tons`;
}

// The live-retrieved figures every competitor gets, model-predicted or estimator-added alike — win rate / bid rate
// (each scoped 3 ways: state, county, project type), capacity (this-year pace vs. historical
// average), and pit access (nearest usable pit + count/quality within 25mi).
function CompetitorStatsBlock({ stats }: { stats?: CompetitorStats }) {
  if (!stats) return null;
  const { win_rate, bid_rate, capacity, pit_access } = stats;
  if (!win_rate && !bid_rate && !capacity && !pit_access) return null;

  return (
    <div className="mt-2 grid grid-cols-1 gap-1.5 border-t border-black/[0.06] pt-2 text-[11px] sm:grid-cols-2">
      {win_rate && (
        <div>
          <div className="font-medium text-foreground/70">Win rate</div>
          <div className="text-muted-foreground">
            State {fmtScoped(win_rate.state)} · County {fmtScoped(win_rate.county)} · Type {fmtScoped(win_rate.project_type)}
          </div>
        </div>
      )}
      {bid_rate && (
        <div>
          <div className="font-medium text-foreground/70">Bid rate</div>
          <div className="text-muted-foreground">
            State {fmtScoped(bid_rate.state)} · County {fmtScoped(bid_rate.county)} · Type {fmtScoped(bid_rate.project_type)}
          </div>
        </div>
      )}
      {capacity && (
        <div>
          <div className="font-medium text-foreground/70">Capacity</div>
          <div className="text-muted-foreground">
            {capacity.typical_capacity
              ? `${fmtTons(capacity.ytd_won)} of ${fmtTons(capacity.typical_capacity)} typical · ${fmtPct(capacity.capacity_pct)}`
              : `${fmtTons(capacity.ytd_won)} so far — no historical baseline yet`}
            {capacity.last_year_total != null && ` (last year: ${fmtTons(capacity.last_year_total)})`}
          </div>
        </div>
      )}
      {pit_access && (
        <div>
          <div className="font-medium text-foreground/70">Pit access</div>
          <div className="text-muted-foreground">
            {pit_access.nearest_pit
              ? `${pit_access.nearest_pit.name} · ${pit_access.nearest_pit.distance_miles.toFixed(1)}mi · quality ${pit_access.nearest_pit.quality ?? "—"}`
              : "No usable pit found"}
            {" · "}{pit_access.pits_within_25mi_count} within 25mi
            {pit_access.pits_within_25mi_avg_quality != null && ` (avg quality ${pit_access.pits_within_25mi_avg_quality.toFixed(1)})`}
          </div>
        </div>
      )}
    </div>
  );
}
