import { HashRouter, Routes, Route } from "react-router-dom";
import { CouncillorProvider } from "./components/CouncillorModal";
import { Logo } from "./components/Logo";
import { SiteNav } from "./components/SiteNav";
import { HomePage } from "./pages/HomePage";
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
            <Route path="/" element={<HomePage />} />
            <Route path="/map" element={<MapPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/contact" element={<ContactPage />} />
          </Routes>
        </div>
      </CouncillorProvider>
    </HashRouter>
  );
}
