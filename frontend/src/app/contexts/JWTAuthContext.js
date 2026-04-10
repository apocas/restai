import { createContext, useEffect, useReducer } from "react";
import axios from "axios";
import { MatxLoading } from "app/components";

const initialState = {
  user: null,
  isInitialized: false,
  isAuthenticated: false,
  isImpersonating: false,
};

function assignRole(user) {
  if (user.is_admin) user.role = "ADMIN";
  else if (user.admin_teams && user.admin_teams.length > 0) user.role = "TEAM_ADMIN";
  else user.role = "USER";
}

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
  verifyTotp: () => {},
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

      const data = response.data;

      // 2FA required — return token for TOTP verification
      if (data.requires_totp) {
        return { requires_totp: true, totp_token: data.totp_token };
      }

      // Normal login — fetch user profile
      const whoami = await axios.get(`${apiUrl}/auth/whoami`, { withCredentials: true });
      const user = whoami.data;
      assignRole(user);

      dispatch({ type: "INIT", payload: { isAuthenticated: true, user, isImpersonating: false } });
      return { requires_totp: false };
    } catch (err) {
      const detail = err.response?.data?.detail || "Login failed. Check your credentials.";
      throw new Error(detail);
    }
  };

  const verifyTotp = async (token, code) => {
    try {
      await axios.post(`${apiUrl}/auth/verify-totp`, { token, code }, { withCredentials: true });
      const whoami = await axios.get(`${apiUrl}/auth/whoami`, { withCredentials: true });
      const user = whoami.data;
      assignRole(user);
      dispatch({ type: "INIT", payload: { isAuthenticated: true, user, isImpersonating: false } });
    } catch (err) {
      const detail = err.response?.data?.detail || "Invalid code.";
      throw new Error(detail);
    }
  };

  const checkAuth = async () => {
    try {
      const response = await axios.get(`${apiUrl}/auth/whoami`, { withCredentials: true });
      const user = response.data;
      assignRole(user);
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
        assignRole(user);
        dispatch({ type: "INIT", payload: { isAuthenticated: true, user, isImpersonating: user.impersonating || false } });
      } catch (err) {
        console.error(err);
        dispatch({ type: "INIT", payload: { isAuthenticated: false, user: null, isImpersonating: false } });
      }
    })();
  }, []);

  if (!state.isInitialized) return <MatxLoading />;

  return (
    <AuthContext.Provider value={{ ...state, method: "JWT", login, verifyTotp, checkAuth, logout, impersonate, exitImpersonation }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
