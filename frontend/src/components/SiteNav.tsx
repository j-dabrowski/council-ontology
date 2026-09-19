import { NavLink } from "react-router-dom";
import { currentCouncil, useCouncilList } from "../councils";

export function SiteNav() {
  const cls = ({ isActive }: { isActive: boolean }) =>
    `nav-link${isActive ? " nav-link-active" : ""}`;
  // Council-scoped routes (App.tsx's "/c/:council") need the active council
  // in the link itself — read from the route (currentCouncil()), same as
  // api.ts, rather than duplicating it in this component's own state.
  const council = currentCouncil();
  // Jurisdiction cue on the persistent, site-wide chrome (docs/uplift/
  // migration/01-known-defects.md G-39) — a reader arriving via a shared
  // panel link, not just a visit to /about, sees which state/territory's
  // law the panel's Nolan/CIPFA/statutory citations are assessed against.
  // Per-council data (currentCouncil()'s own fallback default is the only
  // reason this ever resolves on a non-council page), never a hardcoded
  // label — a future council in a different jurisdiction renders correctly.
  const { list } = useCouncilList();
  const state = list.find((c) => c.key === council)?.state;

  return (
    <nav className="site-nav" aria-label="Main navigation">
      {/* No `end`: "Report" covers the whole council-scoped section
          (Overview/Analysis/History/Lookup/Method under "/c/:council/*"),
          not just the index page — it should stay highlighted on
          /c/<council>/analysis etc., not go blank the moment you leave
          Overview. */}
      <NavLink to={`/c/${council}`} className={cls}>Report</NavLink>
      <NavLink to="/map" className={cls}>Map</NavLink>
      <NavLink to="/about" className={cls}>About</NavLink>
      <NavLink to="/contact" className={cls}>Contact</NavLink>
      {state && <span className="site-nav-jurisdiction">{state}</span>}
    </nav>
  );
}
