import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

const apiUrl = (import.meta.env.VITE_API_URL as string | undefined)?.trim();
if (apiUrl) {
  try {
    const origin = new URL(apiUrl).origin;
    for (const rel of ["preconnect", "dns-prefetch"] as const) {
      const link = document.createElement("link");
      link.rel = rel;
      link.href = origin;
      document.head.appendChild(link);
    }
  } catch {
    // Ignore invalid VITE_API_URL at build/runtime.
  }
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>
);
