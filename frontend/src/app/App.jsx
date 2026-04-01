import { useRoutes } from "react-router-dom";
import CssBaseline from "@mui/material/CssBaseline";

import { MatxTheme } from "./components";

import { AuthProvider } from "./contexts/JWTAuthContext";
import SettingsProvider from "./contexts/SettingsContext";
import PlatformProvider from "./contexts/PlatformContext";
import { TeamBrandingProvider } from "./contexts/TeamBrandingContext";
import ErrorBoundary from "./components/ErrorBoundary";

import routes from "./routes";

export default function App() {
  const content = useRoutes(routes);

  return (
    <ErrorBoundary>
      <PlatformProvider>
        <SettingsProvider>
          <AuthProvider>
            <TeamBrandingProvider>
              <MatxTheme>
                <CssBaseline />
                {content}
              </MatxTheme>
            </TeamBrandingProvider>
          </AuthProvider>
        </SettingsProvider>
      </PlatformProvider>
    </ErrorBoundary>
  );
}
