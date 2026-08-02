"use client";

import { useEffect } from "react";
import { Eyebrow } from "@/components/kit";
import { useProjectsStore } from "@/components/projects/use-projects-store";
import { ProjectsTable } from "@/components/projects/projects-table";

export default function ProjectsPage() {
  const store = useProjectsStore();

  useEffect(() => {
    store.fetchProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="mx-auto max-w-6xl p-6">
      <Eyebrow>Data · Projects</Eyebrow>
      <h1 className="mt-1 font-serif text-2xl tracking-tight">Projects</h1>
      <p className="mt-1 max-w-xl text-[13px] text-muted-foreground">
        Every historical letting, one row per project. Material-quantity columns are editable —
        everything else (identity, location, type, low bid) is read-only here.
      </p>

      <div className="mt-4">
        <ProjectsTable store={store} />
      </div>
    </div>
  );
}
