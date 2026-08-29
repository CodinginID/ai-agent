import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { initSwUpdate } from "./net/swUpdate";
import "./theme/tokens.css";
import "./index.css";

const el = document.getElementById("root");
if (!el) throw new Error("#root not found");

// Sekali di sini (bukan efek React) → StrictMode double-invoke tak relevan;
// initSwUpdate() sendiri tetap dijaga guard `initialized` untuk keamanan ekstra.
initSwUpdate();

createRoot(el).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
