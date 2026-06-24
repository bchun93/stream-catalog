import { ApiWakeBanner } from "./components/ApiWakeBanner";
import { Sidebar } from "./components/layout/Sidebar";
import { ApiWakeProvider } from "./context/ApiWakeContext";
import { Route, Routes } from "react-router-dom";
import { AITrainingPage } from "./pages/AITrainingPage";
import { AssetsPage } from "./pages/AssetsPage";
import { DashboardPage } from "./pages/DashboardPage";
import { MetadataConfigPage } from "./pages/MetadataConfigPage";
import { StoragePage } from "./pages/StoragePage";
import { TitlesPage } from "./pages/TitlesPage";

export default function App() {
  return (
    <ApiWakeProvider>
      <div className="app-shell">
        <Sidebar />
        <div className="app-content">
          <ApiWakeBanner />
          <main className="main">
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/titles" element={<TitlesPage />} />
              <Route path="/metadata-config" element={<MetadataConfigPage />} />
              <Route path="/assets" element={<AssetsPage />} />
              <Route path="/storage" element={<StoragePage />} />
              <Route path="/ai-training" element={<AITrainingPage />} />
            </Routes>
          </main>
        </div>
      </div>
    </ApiWakeProvider>
  );
}
