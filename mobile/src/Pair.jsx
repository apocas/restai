import React, { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { parsePayload, whoami } from "./pairing";

export default function Pair({ onPaired }) {
  const [error, setError] = useState(null);
  const [validating, setValidating] = useState(false);
  const [cameraFailed, setCameraFailed] = useState(false);
  const [manual, setManual] = useState("");
  const scannerRef = useRef(null);
  const handledRef = useRef(false);

  // Validate a parsed payload against the host before committing.
  const tryPair = async (payload) => {
    if (!payload) {
      setError("That QR / code isn't a valid RESTai pairing payload.");
      handledRef.current = false;
      return;
    }
    setValidating(true);
    setError(null);
    const ok = await whoami(payload.host, payload.apiKey);
    setValidating(false);
    if (ok) {
      onPaired(payload);
    } else {
      setError("Authentication failed. Regenerate the key in RESTai and try again.");
      handledRef.current = false;
    }
  };

  useEffect(() => {
    let cancelled = false;
    const scanner = new Html5Qrcode("reader", { verbose: false });
    scannerRef.current = scanner;

    const onScan = async (decoded) => {
      if (handledRef.current) return;
      handledRef.current = true;
      try {
        await scanner.stop();
      } catch {
        /* ignore */
      }
      tryPair(parsePayload(decoded));
    };

    scanner
      .start({ facingMode: "environment" }, { fps: 10, qrbox: { width: 240, height: 240 } }, onScan, () => {})
      .catch(() => {
        if (!cancelled) setCameraFailed(true);
      });

    return () => {
      cancelled = true;
      const s = scannerRef.current;
      if (s) {
        s.stop().then(() => s.clear()).catch(() => {});
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submitManual = () => {
    handledRef.current = true;
    tryPair(parsePayload(manual));
  };

  return (
    <div className="pair">
      <div className="pair-head">
        <img className="pair-logo" src="/mobile/icons/icon-192.png" alt="RESTai" />
        <h1>RESTai</h1>
        <p>Scan the QR from your project's Mobile tab.</p>
      </div>

      <div id="reader" className={"reader" + (cameraFailed ? " hidden" : "")} />

      {validating && <div className="pair-status">Connecting…</div>}
      {error && <div className="pair-error">{error}</div>}

      {cameraFailed && (
        <div className="pair-status">
          Camera unavailable. Paste the pairing code below instead.
        </div>
      )}

      <details className="manual" open={cameraFailed}>
        <summary>Paste pairing code</summary>
        <textarea
          rows={4}
          placeholder='{"host":"…","project_id":1,"api_key":"…"}'
          value={manual}
          onChange={(e) => setManual(e.target.value)}
        />
        <button className="btn" disabled={!manual.trim() || validating} onClick={submitManual}>
          Pair
        </button>
      </details>
    </div>
  );
}
