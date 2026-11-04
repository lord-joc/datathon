import { Route, Routes } from "react-router";

import { AppHeader } from "@/components/AppHeader";
import { TruthBanner } from "@/components/TruthBanner";
import { ComparePage } from "@/features/compare/ComparePage";
import { GuidePage } from "@/features/guide/GuidePage";
import { ResultsPage } from "@/features/results/ResultsPage";
import { SpacePage } from "@/features/space/SpacePage";

import { NotFoundPage } from "./NotFoundPage";
import { SourcesPage } from "./SourcesPage";

export function App() {
  return (
    <div
      className="flex min-h-[100dvh] flex-col"
      style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
    >
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-3 focus:py-2 focus:text-text"
      >
        Preskoči na sadržaj
      </a>
      <AppHeader />
      <TruthBanner />
      <main id="main" className="page-gutter flex-1">
        <Routes>
          <Route path="/" element={<GuidePage />} />
          <Route path="/rezultati/:runId" element={<ResultsPage />} />
          <Route path="/rezultati/:runId/usporedba" element={<ComparePage />} />
          <Route path="/prostor/:spaceId" element={<SpacePage />} />
          <Route path="/izvori" element={<SourcesPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </main>
      <footer className="page-gutter border-t border-border bg-surface py-5 text-sm text-muted">
        <div className="mx-auto grid max-w-6xl gap-1">
          <p>
            Projekt izrađen na Datathonu Portala otvorenih podataka 2026. ProstorIQ nije služba
            Grada Zagreba ni državne uprave.
          </p>
          <p>
            Podaci:{" "}
            <a
              href="https://data.gov.hr"
              className="text-accent underline underline-offset-2 hover:text-accent-strong"
              target="_blank"
              rel="noopener noreferrer"
            >
              data.gov.hr
            </a>
            , Grad Zagreb i OpenStreetMap. Udaljenosti su zračne, nisu vrijeme hoda.
          </p>
        </div>
      </footer>
    </div>
  );
}
