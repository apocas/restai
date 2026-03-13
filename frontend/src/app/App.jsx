import { useRoutes } from "react-router-dom";
import CssBaseline from "@mui/material/CssBaseline";

import { MatxTheme } from "./components";

import { AuthProvider } from "./contexts/JWTAuthContext";
import SettingsProvider from "./contexts/SettingsContext";
import PlatformProvider from "./contexts/PlatformContext";

import routes from "./routes";

export default function App() {
  const content = useRoutes(routes);

  return (
    <PlatformProvider>
      <SettingsProvider>
        <AuthProvider>
          <MatxTheme>
            <CssBaseline />
            {content}
          </MatxTheme>
        </AuthProvider>
      </SettingsProvider>
    </PlatformProvider>
  );
}
