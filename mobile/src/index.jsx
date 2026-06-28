import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")).render(<App />);

// Register the PWA service worker (scoped to /mobile/).
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/mobile/service-worker.js", { scope: "/mobile/" })
      .catch(() => {});
  });
}
