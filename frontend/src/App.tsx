import { NavLink, Route, Routes } from "react-router-dom";
import { AssetsPage } from "./pages/AssetsPage";
import { DashboardPage } from "./pages/DashboardPage";
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
          <NavLink to="/assets">Media assets</NavLink>
        </nav>
        <p style={{ color: "var(--muted)", fontSize: "0.8rem", marginTop: "auto" }}>
          TM + MAM for streaming
        </p>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/titles" element={<TitlesPage />} />
          <Route path="/assets" element={<AssetsPage />} />
        </Routes>
      </main>
    </div>
  );
}
