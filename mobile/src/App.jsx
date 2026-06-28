import React, { useState } from "react";
import { loadCreds, saveCreds, clearCreds } from "./pairing";
import Pair from "./Pair";
import Chat from "./Chat";

// Credential presence decides the screen (mirrors the Android MainActivity):
// none → pairing, present → chat.
export default function App() {
  const [creds, setCreds] = useState(() => loadCreds());

  if (!creds) {
    return <Pair onPaired={(c) => { saveCreds(c); setCreds(c); }} />;
  }
  return (
    <Chat
      creds={creds}
      onUnpair={() => { clearCreds(); setCreds(null); }}
    />
  );
}
