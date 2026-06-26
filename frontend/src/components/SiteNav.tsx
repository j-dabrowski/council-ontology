import { NavLink } from "react-router-dom";

export function SiteNav() {
  const cls = ({ isActive }: { isActive: boolean }) =>
    `nav-link${isActive ? " nav-link-active" : ""}`;

  return (
    <nav className="site-nav" aria-label="Main navigation">
      <NavLink to="/" end className={cls}>Home</NavLink>
      <NavLink to="/map" className={cls}>Map</NavLink>
      <NavLink to="/about" className={cls}>About</NavLink>
      <NavLink to="/contact" className={cls}>Contact</NavLink>
    </nav>
  );
}
