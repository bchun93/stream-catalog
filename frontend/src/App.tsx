import { useEffect, useState } from "react";
import { Menu } from "lucide-react";
import { Route, Routes, useLocation } from "react-router-dom";
import { ApiWakeBanner } from "./components/ApiWakeBanner";
import { RelayMark } from "./components/brand/RelayMark";
import { Sidebar } from "./components/layout/Sidebar";
import { ApiWakeProvider } from "./context/ApiWakeContext";
import { AITrainingPage } from "./pages/AITrainingPage";
import { AssetsPage } from "./pages/AssetsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { DeliveryPage } from "./pages/DeliveryPage";
import { MetadataConfigPage } from "./pages/MetadataConfigPage";
import { StoragePage } from "./pages/StoragePage";
import { TitlesPage } from "./pages/TitlesPage";

export default function App() {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.body.classList.toggle("nav-open", navOpen);
    return () => document.body.classList.remove("nav-open");
  }, [navOpen]);

  return (
    <ApiWakeProvider>
      <div className="app-shell">
        <button
          type="button"
          className={`sidebar-backdrop${navOpen ? " visible" : ""}`}
          aria-label="Close menu"
          tabIndex={navOpen ? 0 : -1}
          onClick={() => setNavOpen(false)}
        />
        <Sidebar
          onNavigate={() => setNavOpen(false)}
          onClose={() => setNavOpen(false)}
        />
        <div className="app-content">
          <header className="mobile-top-bar">
            <button
              type="button"
              className="mobile-nav-toggle"
              aria-label="Open menu"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(true)}
            >
              <Menu size={22} strokeWidth={2} aria-hidden />
            </button>
            <div className="mobile-top-bar-brand">
              <span className="mobile-top-bar-mark" aria-hidden>
                <RelayMark />
              </span>
              <span>Relay</span>
            </div>
          </header>
          <ApiWakeBanner />
          <main className="main">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/titles" element={<TitlesPage />} />
              <Route path="/metadata-config" element={<MetadataConfigPage />} />
              <Route path="/assets" element={<AssetsPage />} />
              <Route path="/delivery" element={<DeliveryPage />} />
              <Route path="/storage" element={<StoragePage />} />
              <Route path="/ai-training" element={<AITrainingPage />} />
            </Routes>
          </main>
        </div>
      </div>
    </ApiWakeProvider>
  );
}
