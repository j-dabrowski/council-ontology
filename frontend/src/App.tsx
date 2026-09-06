import { HashRouter, Routes, Route, Navigate } from "react-router-dom";
import { CouncillorProvider } from "./components/CouncillorModal";
import { DevModeSwitch } from "./components/DevModeSwitch";
import { Logo } from "./components/Logo";
import { SiteNav } from "./components/SiteNav";
import { OverviewPage } from "./pages/OverviewPage";
import { AnalysisPage } from "./pages/AnalysisPage";
import { WatchPage } from "./pages/WatchPage";
import { EvidencePage } from "./pages/EvidencePage";
import { MapPage } from "./pages/MapPage";
import { AboutPage } from "./pages/AboutPage";
import { ContactPage } from "./pages/ContactPage";

export default function App() {
  return (
    <HashRouter>
      <CouncillorProvider>
        <div className="site-layout">
          {import.meta.env.DEV && <DevModeSwitch />}
          <header className="site-header">
            <div className="header-inner">
              <Logo />
              <SiteNav />
            </div>
          </header>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/watch" element={<WatchPage />} />
            <Route path="/digest" element={<Navigate to="/watch" replace />} />
            <Route path="/evidence" element={<EvidencePage />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/contact" element={<ContactPage />} />
          </Routes>
        </div>
      </CouncillorProvider>
    </HashRouter>
  );
}
