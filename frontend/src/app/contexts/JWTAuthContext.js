import { createContext, useEffect, useReducer } from "react";
import axios from "axios";
import { MatxLoading } from "app/components";

const initialState = {
  user: null,
  isInitialized: false,
  isAuthenticated: false,
  isImpersonating: false,
};

const reducer = (state, action) => {
  switch (action.type) {
    case "INIT": {
      const { isAuthenticated, user, isImpersonating } = action.payload;
      return { ...state, isAuthenticated, isInitialized: true, user, isImpersonating: isImpersonating || false };
    }

    case "LOGIN": {
      return { ...state, isAuthenticated: true, user: action.payload.user };
    }

    case "LOGOUT": {
      return { ...state, isAuthenticated: false, user: null, isImpersonating: false };
    }

    default:
      return state;
  }
};

const AuthContext = createContext({
  ...initialState,
  method: "JWT",
  login: () => {},
  checkAuth: () => {},
  logout: () => {},
  impersonate: () => {},
  exitImpersonation: () => {},
});

export const AuthProvider = ({ children }) => {
  const [state, dispatch] = useReducer(reducer, initialState);

  const apiUrl = process.env.REACT_APP_RESTAI_API_URL || "";

  const login = async (email, password) => {
    try {
      const response = await axios.post(
        `${apiUrl}/auth/login`,
        {},
        { auth: { username: email, password: password } }
      );

      const user = response.data;
      user.role = user.is_admin ? "ADMIN" : "USER";

      dispatch({ type: "INIT", payload: { isAuthenticated: true, user, isImpersonating: false } });
    } catch (err) {
      const detail = err.response?.data?.detail || "Login failed. Check your credentials.";
      throw new Error(detail);
    }
  };

  const checkAuth = async () => {
    try {
      const response = await axios.get(`${apiUrl}/auth/whoami`, { withCredentials: true });
      const user = response.data;
      user.role = user.is_admin ? "ADMIN" : "USER";
      dispatch({ type: "INIT", payload: { isAuthenticated: true, user, isImpersonating: user.impersonating || false } });
    } catch (err) {
      dispatch({ type: "LOGOUT" });
    }
  };

  const logout = () => {
    localStorage.removeItem("user");
    axios.post(`${apiUrl}/auth/logout`, {}, { withCredentials: true }).catch(console.error);
    dispatch({ type: "LOGOUT" });
  };

  const impersonate = async (username) => {
    try {
      await axios.post(`${apiUrl}/auth/impersonate/${username}`, {}, { withCredentials: true });
      await checkAuth();
    } catch (err) {
      console.error("Impersonation failed:", err);
    }
  };

  const exitImpersonation = async () => {
    try {
      await axios.post(`${apiUrl}/auth/exit-impersonation`, {}, { withCredentials: true });
      await checkAuth();
    } catch (err) {
      console.error("Exit impersonation failed:", err);
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const response = await axios.get(`${apiUrl}/auth/whoami`, { withCredentials: true });
        const user = response.data;
        user.role = user.is_admin ? "ADMIN" : "USER";
        dispatch({ type: "INIT", payload: { isAuthenticated: true, user, isImpersonating: user.impersonating || false } });
      } catch (err) {
        console.error(err);
        dispatch({ type: "INIT", payload: { isAuthenticated: false, user: null, isImpersonating: false } });
      }
    })();
  }, []);

  if (!state.isInitialized) return <MatxLoading />;

  return (
    <AuthContext.Provider value={{ ...state, method: "JWT", login, checkAuth, logout, impersonate, exitImpersonation }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
