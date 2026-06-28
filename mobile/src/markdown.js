// Strip <think>…</think> reasoning blocks — complete pairs anywhere, plus an
// unclosed trailing block (so live-streaming chunks never flash chain-of-thought).
export function stripThink(text) {
  if (!text) return text;
  let out = text.replace(/<think>[\s\S]*?<\/think>/gi, "");
  const open = out.toLowerCase().lastIndexOf("<think>");
  if (open !== -1 && out.toLowerCase().indexOf("</think>", open) === -1) {
    out = out.slice(0, open);
  }
  return out;
}

// Rewrite relative image references to the paired host so protected endpoints
// (e.g. the agent's /image/cache/<id>.png output) resolve. Mirrors the Android
// MarkdownText behavior: `![](/x)` → `![](host/x)`, and bare relative image
// paths get promoted to images.
export function rewriteRelativeImages(md, host) {
  if (!md) return md;
  let out = md.replace(/!\[([^\]]*)\]\((\/[^)\s]+)\)/g, (_m, alt, path) => `![${alt}](${host}${path})`);
  out = out.replace(
    /(^|\s)(\/image\/cache\/[^\s)]+\.(?:png|jpe?g|gif|webp))/gi,
    (_m, pre, path) => `${pre}![](${host}${path})`
  );
  return out;
}
