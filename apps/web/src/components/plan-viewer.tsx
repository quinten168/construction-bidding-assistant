"use client";

import { useEffect, useRef } from "react";
import { motion } from "motion/react";
import { PAGE_TEXT, PLAN } from "@/lib/mock-plan";

// The right pane: a stand-in "PDF page" that highlights the verbatim evidence when
// a gotcha/field is selected. Swap PAGE_TEXT for react-pdf + a text-layer highlight
// when wiring real PDFs — the selection contract (page + evidence) stays identical.
export function PlanViewer({
  page,
  evidence,
}: {
  page: number | null;
  evidence: string | null;
}) {
  const markRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (markRef.current) {
      markRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [page, evidence]);

  const text = page ? PAGE_TEXT[page] ?? "(page text not in mock corpus)" : null;

  return (
    <div className="glass sheen flex h-full flex-col rounded-2xl">
      <div className="flex items-center justify-between border-b border-black/5 px-4 py-2.5">
        <span className="font-serif text-sm font-medium">Plan viewer</span>
        <span className="font-mono text-xs text-muted-foreground">
          {page ? `${PLAN.id}  ·  p.${page} / ${PLAN.pages}` : "select a finding →"}
        </span>
      </div>

      <div className="flex-1 overflow-auto p-5">
        {!page ? (
          <div className="flex h-full items-center justify-center text-center text-sm text-muted-foreground">
            Click any gotcha or extracted field to see the
            <br /> exact sentence in the plan that proves it.
          </div>
        ) : (
          <motion.div
            key={page}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mx-auto max-w-prose rounded-lg border bg-background/60 p-6 font-mono text-[13px] leading-relaxed shadow-inner"
          >
            {renderWithHighlight(text!, evidence, markRef)}
          </motion.div>
        )}
      </div>
    </div>
  );
}

// Split the page text around the evidence substring and wrap the match in a flashing mark.
function renderWithHighlight(
  text: string,
  evidence: string | null,
  ref: React.RefObject<HTMLSpanElement | null>,
) {
  if (!evidence) return <span className="whitespace-pre-wrap">{text}</span>;
  const idx = text.indexOf(evidence);
  if (idx === -1) return <span className="whitespace-pre-wrap">{text}</span>;

  return (
    <span className="whitespace-pre-wrap">
      {text.slice(0, idx)}
      <span ref={ref} className="prov-highlight px-0.5">
        {evidence}
      </span>
      {text.slice(idx + evidence.length)}
    </span>
  );
}
