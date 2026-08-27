import { HashRouter, Routes, Route } from "react-router-dom";
import { CouncillorProvider } from "./components/CouncillorModal";
import { Logo } from "./components/Logo";
import { SiteNav } from "./components/SiteNav";
import { OverviewPage } from "./pages/OverviewPage";
import { AnalysisPage } from "./pages/AnalysisPage";
import { DigestPage } from "./pages/DigestPage";
import { EvidencePage } from "./pages/EvidencePage";
import { MapPage } from "./pages/MapPage";
import { AboutPage } from "./pages/AboutPage";
import { ContactPage } from "./pages/ContactPage";

export default function App() {
  return (
    <HashRouter>
      <CouncillorProvider>
        <div className="site-layout">
          <header className="site-header">
            <div className="header-inner">
              <Logo />
              <SiteNav />
            </div>
          </header>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/analysis" element={<AnalysisPage />} />
            <Route path="/digest" element={<DigestPage />} />
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
