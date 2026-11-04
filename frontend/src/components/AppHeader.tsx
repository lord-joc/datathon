import { Compass, Database, Moon, Sun } from "lucide-react";
import { NavLink } from "react-router";

import { toggleTheme, useTheme } from "@/lib/theme";

import { SiteSearch } from "./SiteSearch";
import { SystemStatusBadge } from "./SystemStatusBadge";

/** ProstorIQ mark: a floor plan with one highlighted room (our own sign, not a state symbol). */
function Mark() {
  return (
    <svg viewBox="0 0 40 40" width="40" height="40" aria-hidden="true" className="shrink-0">
      <rect width="40" height="40" rx="7" fill="#fff" />
      <path
        d="M9 9h22v22H9zM9 20h11M20 9v16M24 25h7"
        fill="none"
        style={{ stroke: "rgb(var(--bar))" }}
        strokeWidth="2.6"
        strokeLinejoin="round"
      />
      <rect x="21.5" y="10.5" width="8" height="8" rx="1" style={{ fill: "rgb(var(--bar))" }} />
    </svg>
  );
}

const tile =
  "inline-flex min-h-touch items-center gap-2 rounded-md px-3 text-sm font-medium transition-colors";

export function AppHeader() {
  const theme = useTheme();
  const dark = theme === "dark";
  return (
    <header
      className="sticky z-20 bg-bar text-on-bar shadow-[0_1px_0_rgb(0_0_0/0.15)]"
      style={{ top: "env(safe-area-inset-top, 0px)" }}
    >
      <div className="page-gutter mx-auto grid max-w-6xl grid-cols-[1fr_auto] items-center gap-x-4 gap-y-3 py-3 md:grid-cols-[auto_minmax(0,1fr)_auto]">
        <NavLink
          to="/"
          className="flex min-h-touch items-center gap-3 rounded-md md:col-start-1 md:row-start-1"
        >
          <Mark />
          <span className="grid leading-tight">
            <span className="text-xl font-bold tracking-tight">ProstorIQ</span>
            <span className="hidden text-sm text-on-bar/85 sm:block">
              Gradski poslovni prostori u Zagrebu
            </span>
          </span>
        </NavLink>

        <SiteSearch className="col-span-2 row-start-2 md:col-span-1 md:col-start-2 md:row-start-1 md:mx-auto md:w-full md:max-w-xl" />

        <nav
          aria-label="Glavna navigacija"
          className="flex items-center justify-end gap-1 md:col-start-3 md:row-start-1"
        >
          <SystemStatusBadge />
          <NavLink
            to="/"
            end
            aria-label="Vodič"
            className={({ isActive }) =>
              `${tile} ${isActive ? "bg-white/20" : "hover:bg-white/15"}`
            }
          >
            <Compass aria-hidden="true" size={18} />
            <span className="hidden lg:inline">Vodič</span>
          </NavLink>
          <NavLink
            to="/izvori"
            aria-label="Izvori podataka"
            className={({ isActive }) =>
              `${tile} ${isActive ? "bg-white/20" : "hover:bg-white/15"}`
            }
          >
            <Database aria-hidden="true" size={18} />
            <span className="hidden lg:inline">Izvori</span>
          </NavLink>
          <button
            type="button"
            onClick={toggleTheme}
            className={`${tile} hover:bg-white/15`}
            aria-label={dark ? "Uključi svijetli prikaz" : "Uključi tamni prikaz"}
            title={dark ? "Svijetli prikaz" : "Tamni prikaz"}
          >
            {dark ? <Sun aria-hidden="true" size={18} /> : <Moon aria-hidden="true" size={18} />}
          </button>
        </nav>
      </div>
    </header>
  );
}
