import "./captureClock"; // must run before any animation library loads
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./styles/theme.css";
import "./styles/app.css";
import "./styles/flow.css";
import "./styles/home.css";
import "./styles/capture.css";
import "./styles/export.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
