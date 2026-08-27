import { useState } from "react";
import { NavLink } from "react-router-dom";

export function CouncilHeader() {
  const [council, setCouncil] = useState("cambridge");
  const cls = ({ isActive }: { isActive: boolean }) =>
    `council-subnav-link${isActive ? " council-subnav-link-active" : ""}`;

  return (
    <div className="home-council-header">
      <h1 className="site-title">
        City of{" "}
        <span className="council-select-wrap">
          <select
            className="council-select"
            value={council}
            onChange={e => setCouncil(e.target.value)}
          >
            <option value="cambridge">Cambridge</option>
          </select>
        </span>
        {" "}Council
      </h1>
      <p className="site-subtitle">
        Analysis of meeting minutes · 1995–2026 ·{" "}
        <span className="data-note">Full 30-year corpus</span>
      </p>
      <nav className="council-subnav" aria-label="Report sections">
        <NavLink to="/" end className={cls}>Overview</NavLink>
        <NavLink to="/analysis" className={cls}>Analysis</NavLink>
        <NavLink to="/digest" className={cls}>Digest</NavLink>
        <NavLink to="/evidence" className={cls}>Evidence</NavLink>
      </nav>
    </div>
  );
}
