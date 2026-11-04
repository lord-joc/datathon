// One variable file per subset instead of three weights x two subsets (Lighthouse, 2026-10-31).
import "@fontsource-variable/inter/index.css";
import "@fontsource/jetbrains-mono/400.css";
import "./styles/index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";

import { App } from "./app/App";
import { initSpotlight } from "./lib/spotlight";
import { initTheme } from "./lib/theme";

// Before the first render, so the page never flashes the other theme.
initTheme();
initSpotlight();

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false } },
});

const root = document.getElementById("root");
if (!root) throw new Error("Nedostaje #root element.");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
