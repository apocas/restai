// RFC 4180 CSV field escape: wrap in quotes when the value contains a
// quote, comma, or newline; escape inner quotes by doubling them.
function escapeCell(v) {
  if (v == null) return "";
  const s = typeof v === "string" ? v : (typeof v === "object" ? JSON.stringify(v) : String(v));
  if (/[",\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

/**
 * Build a CSV string from an array of row objects.
 *
 * @param {object[]} rows — data rows
 * @param {Array<{key: string, header?: string, get?: (row) => any}>} columns
 *   `get` takes precedence over `row[key]`; `header` falls back to `key`.
 * @returns {string} CSV with CRLF line endings (Excel-friendly).
 */
export function toCsv(rows, columns) {
  const headerLine = columns.map((c) => escapeCell(c.header || c.key)).join(",");
  const dataLines = rows.map((r) =>
    columns.map((c) => escapeCell(c.get ? c.get(r) : r[c.key])).join(",")
  );
  // Excel on Windows reads CRLF more reliably than LF, and Excel-on-Mac
  // handles either — CRLF is the safe default.
  return [headerLine, ...dataLines].join("\r\n");
}

/**
 * Trigger a browser download of the given CSV content. `filename` gets a
 * `.csv` suffix if not already present.
 */
export function downloadCsv(filename, csv) {
  const name = filename.endsWith(".csv") ? filename : `${filename}.csv`;
  // `﻿` BOM so Excel on Windows auto-detects UTF-8. Harmless for
  // other tooling — pandas / Numbers / Sheets strip the BOM on read.
  const blob = new Blob(["﻿", csv], { type: "text/csv;charset=utf-8;" });
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Give the browser a tick before revoking so the download actually fires.
  setTimeout(() => URL.revokeObjectURL(href), 0);
}
