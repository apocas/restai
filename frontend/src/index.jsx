import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import * as serviceWorker from "./serviceWorker";
import App from "./app/App";

// Initialize i18next before any component renders so the first paint is
// already in the user's preferred language (LanguageDetector resolves
// from localStorage → navigator → fallback `en` at import time).
import "./app/i18n";

import "perfect-scrollbar/css/perfect-scrollbar.css";

const root = createRoot(document.getElementById("root"));

root.render(
  <BrowserRouter basename="/admin">
    <App />
  </BrowserRouter>
);

// for IE-11 support un-comment cssVars() and it's import in this file
// and in MatxTheme file

// If you want your app to work offline and load faster, you can change
// unregister() to register() below. Note this comes with some pitfalls.
// Learn more about service workers: https://bit.ly/CRA-PWA
serviceWorker.unregister();
