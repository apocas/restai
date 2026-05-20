import { createContext, useState, useEffect, useContext, useCallback } from "react";

export const PlatformContext = createContext({
  platformCapabilities: {
    gpu: true,
    sso: [],
    sso_provider_names: {},
    proxy: null,
    app_name: "RESTai",
    hide_branding: false,
    proxy_url: "",
    currency: "EUR",
    auth_disable_local: false,
    mcp: false,
    app_builder: false
  },
  isLoading: true,
  refreshCapabilities: () => {}
});

export const usePlatformCapabilities = () => useContext(PlatformContext);

export default function PlatformProvider({ children }) {
  const [platformCapabilities, setPlatformCapabilities] = useState({
    gpu: true,
    sso: [],
    sso_provider_names: {},
    proxy: null,
    app_name: "RESTai",
    hide_branding: false,
    proxy_url: "",
    currency: "EUR",
    auth_disable_local: false,
    mcp: false,
    app_builder: false
  });
  const [isLoading, setIsLoading] = useState(true);

  const fetchCapabilities = useCallback(async () => {
    try {
      const url = process.env.REACT_APP_RESTAI_API_URL || "";
      const response = await fetch(`${url}/setup`);

      if (response.ok) {
        const data = await response.json();
        setPlatformCapabilities({
          gpu: data.gpu || false,
          sso: data.sso || [],
          sso_provider_names: data.sso_provider_names || {},
          proxy: data.proxy || null,
          app_name: data.app_name || "RESTai",
          logo_url: data.logo_url || "",
          hide_branding: data.hide_branding || false,
          proxy_url: data.proxy_url || "",
          currency: data.currency || "USD",
          auth_disable_local: data.auth_disable_local || false,
          mcp: data.mcp || false,
          // Gates the "app" project type in /projects/new — backend
          // sets this true when app_docker_enabled is on. Default
          // false so the type stays hidden when the runtime isn't ready.
          app_builder: data.app_builder || false,
          // `auth_secret_weak` used to live here but leaked pre-auth via
          // /setup — it now comes from the authenticated /info endpoint
          // and is consumed directly by the admin dashboard.
        });
      } else {
        console.error("Failed to fetch platform capabilities");
      }
    } catch (error) {
      console.error("Error fetching platform capabilities:", error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchCapabilities();
  }, [fetchCapabilities]);

  return (
    <PlatformContext.Provider value={{ platformCapabilities, isLoading, refreshCapabilities: fetchCapabilities }}>
      {children}
    </PlatformContext.Provider>
  );
}
