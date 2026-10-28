import { NavLink } from "react-router";

import { SystemStatusBadge } from "./SystemStatusBadge";

export function AppHeader() {
  return (
    <header
      className="sticky z-20 border-b border-border bg-bg/90 backdrop-blur"
      style={{ top: "env(safe-area-inset-top, 0px)" }}
    >
      <div className="page-gutter mx-auto flex h-14 max-w-6xl items-center justify-between gap-4">
        <NavLink to="/" className="font-display text-lg font-semibold tracking-tight text-text">
          Prostor<span className="text-accent">IQ</span>
        </NavLink>
        <nav aria-label="Glavna navigacija" className="flex items-center gap-1 text-sm">
          <SystemStatusBadge />
          <NavLink
            to="/izvori"
            className={({ isActive }) =>
              `inline-flex min-h-touch items-center rounded-md px-3 ${isActive ? "text-accent" : "text-muted hover:text-text"}`
            }
          >
            Izvori podataka
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
