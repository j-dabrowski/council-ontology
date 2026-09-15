import { HashRouter, Routes, Route, Navigate, Outlet, useParams } from "react-router-dom";
import { CouncillorProvider } from "./components/CouncillorModal";
import { DevModeSwitch } from "./components/DevModeSwitch";
import { Logo } from "./components/Logo";
import { SiteNav } from "./components/SiteNav";
import { useCouncilList, FALLBACK_COUNCIL } from "./councils";
import { OverviewPage } from "./pages/OverviewPage";
import { AnalysisPage } from "./pages/AnalysisPage";
import { WatchPage } from "./pages/WatchPage";
import { MethodPage } from "./pages/MethodPage";
import { MapPage } from "./pages/MapPage";
import { RecordPage } from "./pages/RecordPage";
import { AboutPage } from "./pages/AboutPage";
import { ContactPage } from "./pages/ContactPage";

// The persistent chrome (header, nav, dev-mode switch) — every route sits
// under this, council-scoped or not (/about, /contact included), matching
// the original layout before "/c/:council" existed.
function SiteLayout() {
  return (
    <div className="site-layout">
      {import.meta.env.DEV && <DevModeSwitch />}
      <header className="site-header">
        <div className="header-inner">
          <Logo />
          <SiteNav />
        </div>
      </header>
      <Outlet />
    </div>
  );
}

// The council validity check, nested under "/c/:council" only (SECOND_
// COUNCIL_PLAN.md Phase 3.2: the selected council lives in the route, not
// component state). A `:council` segment that isn't in the real council
// list (a typo, a stale bookmark, an unpublished key) redirects to the
// first real one rather than rendering a page that can only 404 its own
// data fetches.
function CouncilGuard() {
  const { council } = useParams<{ council: string }>();
  const { list, loading } = useCouncilList();

  if (!loading && list.length > 0 && !list.some((c) => c.key === council)) {
    return <Navigate to={`/c/${list[0].key}`} replace />;
  }

  return <Outlet />;
}

// Bare "/" (or anything unmatched below) has no council of its own to carry
// forward — send it to the first council the mode-dependent list actually
// has. FALLBACK_COUNCIL only until that list loads, same bootstrap-only use
// as everywhere else it appears.
function DefaultCouncilRedirect() {
  const { list, loading } = useCouncilList();
  if (loading) return null;
  return <Navigate to={`/c/${list[0]?.key ?? FALLBACK_COUNCIL}`} replace />;
}

export default function App() {
  return (
    <HashRouter>
      <CouncillorProvider>
        <Routes>
          <Route element={<SiteLayout />}>
            <Route path="/c/:council" element={<CouncilGuard />}>
              <Route index element={<OverviewPage />} />
              <Route path="analysis" element={<AnalysisPage />} />
              <Route path="watch" element={<WatchPage />} />
              <Route path="digest" element={<Navigate to="../watch" replace />} />
              <Route path="method" element={<MethodPage />} />
              <Route path="evidence" element={<Navigate to="../method" replace />} />
              <Route path="map" element={<MapPage />} />
              <Route path="record" element={<RecordPage />} />
            </Route>
            {/* Council-list-aware (their own "coverage" content) but not
                council-scoped pages — no reason a link to either should carry
                one council's context, and doing so would just recreate the
                "/:council" vs "/about" ambiguity this shape was chosen to
                avoid. */}
            <Route path="/about" element={<AboutPage />} />
            <Route path="/contact" element={<ContactPage />} />
            <Route path="*" element={<DefaultCouncilRedirect />} />
          </Route>
        </Routes>
      </CouncillorProvider>
    </HashRouter>
  );
}
