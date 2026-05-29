const express = require("express");
const jwt = require("jsonwebtoken");
const path = require("path");

const app = express();
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, "public")));

// POST /token — generate a signed JWT context token
app.post("/token", (req, res) => {
  const { secret, claims, ttl } = req.body;

  if (!secret) return res.status(400).json({ error: "secret is required" });
  if (!claims || typeof claims !== "object") {
    return res.status(400).json({ error: "claims must be a JSON object" });
  }

  const ttlSeconds = parseInt(ttl, 10) || 3600;
  const now = Math.floor(Date.now() / 1000);

  const payload = {
    ...claims,
    iat: now,
    exp: now + ttlSeconds,
  };

  try {
    const token = jwt.sign(payload, secret, { algorithm: "HS256" });
    res.json({ token, payload });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

const PORT = process.env.PORT || 3333;
app.listen(PORT, () => {
  console.log(`Widget context test server running at http://localhost:${PORT}`);
});
