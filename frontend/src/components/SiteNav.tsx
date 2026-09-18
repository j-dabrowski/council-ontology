import { NavLink } from "react-router-dom";
import { currentCouncil } from "../councils";

export function SiteNav() {
  const cls = ({ isActive }: { isActive: boolean }) =>
    `nav-link${isActive ? " nav-link-active" : ""}`;
  // Council-scoped routes (App.tsx's "/c/:council") need the active council
  // in the link itself — read from the route (currentCouncil()), same as
  // api.ts, rather than duplicating it in this component's own state.
  const council = currentCouncil();

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
    </nav>
  );
}
