import { NavLink, useLocation, useNavigate, useParams } from "react-router-dom";
import { useCouncilList, useCorpusSpan } from "../councils";

export function CouncilHeader() {
  const { council } = useParams<{ council: string }>();
  const { list, loading } = useCouncilList();
  const span = useCorpusSpan();
  const navigate = useNavigate();
  const location = useLocation();
  const cls = ({ isActive }: { isActive: boolean }) =>
    `council-subnav-link${isActive ? " council-subnav-link-active" : ""}`;

  const current = list.find((c) => c.key === council);
  const shortName = current?.short_name ?? council ?? "";

  // Switching council keeps the same sub-page (Analysis stays Analysis) —
  // only the council segment of the path changes, and the selection lives
  // in the route itself, not component state (SECOND_COUNCIL_PLAN.md
  // Phase 3.2).
  function handleSelect(key: string) {
    const suffix = location.pathname.replace(/^\/c\/[^/]+/, "");
    navigate(`/c/${key}${suffix}`);
  }

  return (
    <div className="home-council-header">
      {/* name_prefix/name_suffix ("Town of" / "Council") frame the selector
          as fixed plain text either side, but come from the CURRENT
          council's own registry entry — switching to a Shire (a different
          prefix, or none) updates this scaffolding along with the selector
          itself, never a fixed template. */}
      <h1 className="site-title">
        {current?.name_prefix && <>{current.name_prefix}{" "}</>}
        {/* A single real council: plain text, not a one-option dropdown
            (Phase 3.2's explicit instruction) — the common case today. */}
        {loading || list.length <= 1 ? (
          shortName
        ) : (
          <span className="council-select-wrap">
            <select
              className="council-select"
              value={council}
              onChange={(e) => handleSelect(e.target.value)}
            >
              {list.map((c) => (
                <option key={c.key} value={c.key}>{c.short_name}</option>
              ))}
            </select>
          </span>
        )}
        {current?.name_suffix && <>{" "}{current.name_suffix}</>}
      </h1>
      {span && (
        <p className="site-subtitle">
          Analysis of meeting minutes · <span className="data-note">{span}</span>
        </p>
      )}
      <nav className="council-subnav" aria-label="Report sections">
        <NavLink to={`/c/${council}`} end className={cls}>Overview</NavLink>
        <NavLink to={`/c/${council}/analysis`} className={cls}>Analysis</NavLink>
        <NavLink to={`/c/${council}/watch`} className={cls}>History</NavLink>
        <NavLink to={`/c/${council}/record`} className={cls}>Look Up</NavLink>
        <NavLink to={`/c/${council}/method`} className={cls}>Method</NavLink>
      </nav>
    </div>
  );
}
