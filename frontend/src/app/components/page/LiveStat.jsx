import { useEffect, useRef, useState } from "react";
import { Box, Typography } from "@mui/material";
import { FONT_MONO, pulse } from "./pageStyles";

// Count-up number with optional pulse on change. Drop into a hero or a
// stat card to make the dashboard feel alive — value animates from
// `prev` to `value` over ~1s, and the pill briefly glows on every
// settled update so the user can see the number breathe.
//
// `format` is called on every frame, so the parent doesn't need to
// rebuild the formatted string itself.
export default function LiveStat({
  value,
  format = (n) => Math.round(n).toLocaleString(),
  label,
  glyph,
  glyphColor = "#7dd3fc",
  // Override duration of the count-up. Keep it short (~600-1000ms) so
  // it reads as "the data just landed", not as a slow scrub.
  duration = 800,
  sx,
}) {
  const [display, setDisplay] = useState(value || 0);
  const prevRef = useRef(value || 0);
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    const start = prevRef.current;
    const end = Number(value) || 0;
    if (start === end) {
      setDisplay(end);
      return;
    }
    let raf;
    const t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, (t - t0) / duration);
      // Ease-out cubic — number rushes in, settles.
      const eased = 1 - Math.pow(1 - k, 3);
      setDisplay(start + (end - start) * eased);
      if (k < 1) {
        raf = requestAnimationFrame(step);
      } else {
        prevRef.current = end;
        setFlash(true);
        setTimeout(() => setFlash(false), 700);
      }
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  return (
    <Box
      sx={{
        display: "inline-flex",
        flexDirection: "column",
        alignItems: "flex-start",
        ...sx,
      }}
    >
      {label && (
        <Typography
          variant="overline"
          sx={{
            color: "text.secondary",
            letterSpacing: 1.5,
            fontSize: "0.65rem",
            lineHeight: 1.4,
          }}
        >
          {label}
        </Typography>
      )}
      <Box
        sx={{
          display: "inline-flex",
          alignItems: "baseline",
          gap: 0.75,
          fontFamily: FONT_MONO,
          fontWeight: 700,
          fontSize: "1.5rem",
          lineHeight: 1.2,
          color: "text.primary",
          // Brief glow when the value settles. Keep it cyan so it reads
          // as "fresh data" rather than "warning".
          ...(flash && {
            animation: `${pulse} 0.7s ease-out`,
            color: "primary.main",
          }),
          transition: "color 0.4s ease",
        }}
      >
        {glyph && (
          <Box component="span" sx={{ color: glyphColor, fontSize: "0.95rem" }}>
            {glyph}
          </Box>
        )}
        <span>{format(display)}</span>
      </Box>
    </Box>
  );
}
