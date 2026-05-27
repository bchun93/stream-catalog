import { NavLink, Route, Routes } from "react-router-dom";
import { ApiStatus } from "./components/ApiStatus";
import { AITrainingPage } from "./pages/AITrainingPage";
import { AssetsPage } from "./pages/AssetsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { MetadataConfigPage } from "./pages/MetadataConfigPage";
import { TitlesPage } from "./pages/TitlesPage";

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          Stream <span>Catalog</span>
        </div>
        <nav className="nav">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <NavLink to="/titles">Titles</NavLink>
          <NavLink to="/metadata-config">Metadata config</NavLink>
          <NavLink to="/assets">Media assets</NavLink>
          <NavLink to="/ai-training">AI training</NavLink>
        </nav>
        <ApiStatus />
        <p style={{ color: "var(--muted)", fontSize: "0.8rem", marginTop: "0.75rem" }}>
          TM + MAM for streaming
        </p>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/titles" element={<TitlesPage />} />
          <Route path="/metadata-config" element={<MetadataConfigPage />} />
          <Route path="/assets" element={<AssetsPage />} />
          <Route path="/ai-training" element={<AITrainingPage />} />
        </Routes>
      </main>
    </div>
  );
}
