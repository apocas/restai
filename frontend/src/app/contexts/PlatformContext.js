import { createContext, useState, useEffect, useContext } from "react";

export const PlatformContext = createContext({
  platformCapabilities: {
    gpu: true, // Default values
    sso: [],
    proxy: null
  },
  isLoading: true
});

export const usePlatformCapabilities = () => useContext(PlatformContext);

export default function PlatformProvider({ children }) {
  const [platformCapabilities, setPlatformCapabilities] = useState({
    gpu: true,
    sso: [],
    proxy: null
  });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const fetchCapabilities = async () => {
      try {
        const url = process.env.REACT_APP_RESTAI_API_URL || "";
        const response = await fetch(`${url}/setup`);
        
        if (response.ok) {
          const data = await response.json();
          setPlatformCapabilities({
            gpu: data.gpu || false,
            sso: data.sso || [],
            proxy: data.proxy || null
          });
        } else {
          console.error("Failed to fetch platform capabilities");
        }
      } catch (error) {
        console.error("Error fetching platform capabilities:", error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchCapabilities();
  }, []);

  return (
    <PlatformContext.Provider value={{ platformCapabilities, isLoading }}>
      {children}
    </PlatformContext.Provider>
  );
}