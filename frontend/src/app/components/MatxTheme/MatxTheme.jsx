import { useMemo } from "react";
import { CssBaseline, ThemeProvider, createTheme } from "@mui/material";
import useSettings from "app/hooks/useSettings";
import { useTeamBranding } from "app/contexts/TeamBrandingContext";

const MatxTheme = ({ children }) => {
  const { settings } = useSettings();
  const { branding } = useTeamBranding();

  const theme = useMemo(() => {
    const baseTheme = { ...settings.themes[settings.activeTheme] };

    if (!branding || (!branding.primary_color && !branding.secondary_color)) {
      return baseTheme;
    }

    // Overlay team branding colors onto the active theme
    return createTheme({
      ...baseTheme,
      palette: {
        ...baseTheme.palette,
        ...(branding.primary_color && {
          primary: { main: branding.primary_color },
        }),
        ...(branding.secondary_color && {
          secondary: { main: branding.secondary_color },
        }),
      },
    });
  }, [settings, branding]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      {children}
    </ThemeProvider>
  );
};

export default MatxTheme;
