import React, { useEffect, useRef, useState } from "react";
import { Html5Qrcode } from "html5-qrcode";
import { parsePayload, whoami } from "./pairing";

export default function Pair({ onPaired }) {
  const [error, setError] = useState(null);
  const [validating, setValidating] = useState(false);
  const [cameraFailed, setCameraFailed] = useState(false);
  const [manual, setManual] = useState("");
  const scannerRef = useRef(null);
  const runningRef = useRef(false);
  const handledRef = useRef(false);
  const mountedRef = useRef(true);

  // Turn the camera off (without tearing down the instance, so it can restart
  // after a failed scan). Idempotent + guarded: html5-qrcode throws on a
  // double-stop, and an unguarded throw during the Pair → Chat unmount blanked
  // the whole app (the "white screen after pairing" bug).
  const stopCamera = async () => {
    const s = scannerRef.current;
    if (!s || !runningRef.current) return;
    runningRef.current = false;
    try {
      await s.stop();
    } catch {
      /* already stopped / node detached */
    }
  };

  const onScan = async (decoded) => {
    if (handledRef.current) return;
    handledRef.current = true;
    await stopCamera();
    tryPair(parsePayload(decoded));
  };

  const startCamera = async () => {
    const s = scannerRef.current;
    if (!s || runningRef.current) return;
    try {
      await s.start(
        { facingMode: "environment" },
        { fps: 10, qrbox: { width: 240, height: 240 } },
        onScan,
        () => {}
      );
      runningRef.current = true;
    } catch {
      if (mountedRef.current) setCameraFailed(true);
    }
  };

  // Validate a parsed payload against the host before committing. The camera is
  // already stopped by the caller, so a successful pair can unmount cleanly.
  const tryPair = async (payload) => {
    if (!payload) {
      setError("That QR / code isn't a valid RESTai pairing payload.");
      handledRef.current = false;
      startCamera();
      return;
    }
    setValidating(true);
    setError(null);
    const ok = await whoami(payload.host, payload.apiKey);
    if (!mountedRef.current) return;
    setValidating(false);
    if (ok) {
      onPaired(payload);
    } else {
      setError("Authentication failed. Regenerate the key in RESTai and try again.");
      handledRef.current = false;
      startCamera();
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    scannerRef.current = new Html5Qrcode("reader", { verbose: false });
    startCamera();
    return () => {
      mountedRef.current = false;
      const s = scannerRef.current;
      if (!s) return;
      // Stop (only if running) then clear the injected DOM — both guarded
      // because the #reader node may already be detached on unmount.
      Promise.resolve(runningRef.current ? s.stop() : null)
        .catch(() => {})
        .finally(() => {
          try {
            s.clear();
          } catch {
            /* node already removed */
          }
        });
      runningRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submitManual = async () => {
    if (handledRef.current) return;
    handledRef.current = true;
    await stopCamera();
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
