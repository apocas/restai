import { createContext, useEffect, useReducer } from "react";
import axios from "axios";
import { MatxLoading } from "app/components";

const initialState = {
  user: null,
  isInitialized: false,
  isAuthenticated: false
};

const reducer = (state, action) => {
  switch (action.type) {
    case "INIT": {
      const { isAuthenticated, user } = action.payload;
      return { ...state, isAuthenticated, isInitialized: true, user };
    }

    case "LOGIN": {
      return { ...state, isAuthenticated: true, user: action.payload.user };
    }

    case "LOGOUT": {
      return { ...state, isAuthenticated: false, user: null };
    }

    default:
      return state;
  }
};

const AuthContext = createContext({
  ...initialState,
  method: "JWT",
  login: () => { },
  checkAuth: () => { },
  logout: () => { }
});

export const AuthProvider = ({ children }) => {
  const [state, dispatch] = useReducer(reducer, initialState);

  const login = async (email, password) => {
    let basicAuth = "";
    if (email && password) {
      basicAuth = btoa(`${email}:${password}`);
    }

    const response = await axios.post(
      `${process.env.REACT_APP_RESTAI_API_URL || ""}/auth/login`,
      {},
      {
        auth: {
          username: email,
          password: password
        }
      }
    );

    const user = response.data;
    user.role = user.is_admin ? "ADMIN" : "USER";

    dispatch({ type: "INIT", payload: { isAuthenticated: true, user } });
  };

  const checkAuth = async () => {
    try {
      const response = await axios.get(
        `${process.env.REACT_APP_RESTAI_API_URL || ""}/auth/whoami`,
        { withCredentials: true }
      );

      const user = response.data;
      user.role = user.is_admin ? "ADMIN" : "USER";

      dispatch({ type: "INIT", payload: { isAuthenticated: true, user } });
    } catch (err) {
      dispatch({ type: "LOGOUT" });
    }
  };

  const logout = () => {
    localStorage.removeItem("user");
    axios
      .post(
        `${process.env.REACT_APP_RESTAI_API_URL || ""}/auth/logout`,
        {},
        { withCredentials: true }
      )
      .catch(console.error);
    dispatch({ type: "LOGOUT" });
  };

  useEffect(() => {
    (async () => {
      try {
        const response = await axios.get(
          `${process.env.REACT_APP_RESTAI_API_URL || ""}/auth/whoami`,
          { withCredentials: true }
        );

        const user = response.data;
        user.role = user.is_admin ? "ADMIN" : "USER";

        dispatch({ type: "INIT", payload: { isAuthenticated: true, user } });
      } catch (err) {
        console.error(err);
        dispatch({ type: "INIT", payload: { isAuthenticated: false, user: null } });
      }
    })();
  }, []);

  if (!state.isInitialized) return <MatxLoading />;

  return (
    <AuthContext.Provider value={{ ...state, method: "JWT", login, checkAuth, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
