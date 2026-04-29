import { Suspense, lazy, useMemo } from "react";
import { Box, CircularProgress } from "@mui/material";

// Monaco is ~3MB pre-gzip. Lazy-load so the rest of the admin doesn't pay
// for it; only users on the App Builder route pull it in. The named-export
// shape is required by @monaco-editor/react so we wrap in a default-export
// trampoline.
//
// IMPORTANT: by default @monaco-editor/react fetches the Monaco runtime
// from a CDN (cdn.jsdelivr.net), which the admin CSP rightly blocks.
// We ship a local copy under /admin/monaco/vs/ via the `monaco:copy`
// npm script and point loader.config there. RESTai's admin SPA is
// always mounted at /admin/ (see homepage in package.json) so the path
// is stable.
const MonacoEditor = lazy(() =>
  import("@monaco-editor/react").then((m) => {
    try {
      m.loader.config({ paths: { vs: "/admin/monaco/vs" } });
    } catch (_) {
      // Older versions exposed config differently; safe to ignore.
    }
    return { default: m.Editor };
  })
);

// Map file extension -> Monaco language id. Only languages we actually want
// the user to edit; other extensions fall through to plain text.
const LANGUAGE_BY_EXTENSION = {
  ts: "typescript",
  tsx: "typescript",
  js: "javascript",
  jsx: "javascript",
  mjs: "javascript",
  php: "php",
  phtml: "php",
  html: "html",
  htm: "html",
  css: "css",
  scss: "scss",
  json: "json",
  md: "markdown",
  txt: "plaintext",
  svg: "xml",
  sql: "sql",
};

function languageForPath(path) {
  if (!path) return "plaintext";
  const dot = path.lastIndexOf(".");
  if (dot < 0) return "plaintext";
  const ext = path.slice(dot + 1).toLowerCase();
  return LANGUAGE_BY_EXTENSION[ext] || "plaintext";
}

const Loading = () => (
  <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", flexGrow: 1, minHeight: 320 }}>
    <CircularProgress size={28} />
  </Box>
);

export default function AppCodeEditor({ path, value, onChange, readOnly = false }) {
  const language = useMemo(() => languageForPath(path), [path]);

  // Slim "VSCode-lite" options. Hides the noisy chrome (minimap, code lens,
  // suggestion shadows) so the editor feels closer to a code field than to a
  // full IDE. Keep folding + line numbers because they're table stakes.
  const options = useMemo(
    () => ({
      readOnly,
      minimap: { enabled: false },
      lineNumbers: "on",
      fontSize: 13,
      tabSize: 2,
      insertSpaces: true,
      automaticLayout: true,
      scrollBeyondLastLine: false,
      smoothScrolling: true,
      cursorBlinking: "smooth",
      renderLineHighlight: "line",
      wordWrap: "off",
      bracketPairColorization: { enabled: true },
      // No fancy plugin chrome — keep the editor focused on text.
      codeLens: false,
      lightbulb: { enabled: false },
      // The TypeScript / PHP language servers run in a Web Worker; for our
      // sandboxed builder we don't need full project-wide intellisense, so
      // disable the worker-driven suggestions for speed.
      quickSuggestions: { other: true, comments: false, strings: false },
      stickyScroll: { enabled: false },
    }),
    [readOnly]
  );

  return (
    // The outer Box uses BOTH flexGrow:1 and height:100% so Monaco fills
    // its parent in either layout style: a flex column parent (Builder's
    // Pane) honors flexGrow, a non-flex block parent honors height:100%.
    // Pass explicit height/width to MonacoEditor too so @monaco-editor/react
    // never falls back to 'auto' (which collapses to a few pixels).
    <Box sx={{ width: "100%", height: "100%", flexGrow: 1, minHeight: 320, position: "relative" }}>
      <Suspense fallback={<Loading />}>
        <MonacoEditor
          height="100%"
          width="100%"
          language={language}
          value={value}
          onChange={onChange}
          theme="vs-dark"
          options={options}
          loading={<Loading />}
        />
      </Suspense>
    </Box>
  );
}
