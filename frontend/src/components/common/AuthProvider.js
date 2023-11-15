import { useLocalStorage } from "./useLocalStorage";
import React, { createContext } from 'react';
export const AuthContext = createContext();
export const AuthProvider = ({ children }) => {
  const [user, setUser] = useLocalStorage("user", null);
  const login = (username, password) => {
    const url = process.env.REACT_APP_RESTAI_API_URL || "";
    const basicAuth = btoa(username + ":" + password);
    fetch(url + "/users/me", {
      headers: new Headers({ 'Authorization': 'Basic ' + basicAuth }),
    })
      .then((res) => {
        if (res.status === 401) {
          setUser(null)
          return null;
        } else if (res.status === 200) {
          return res.json();
        } else {
          setUser(null)
          return null;
        }
      }).then((res) => {
        if (res !== null)
          setUser({ username: username, basicAuth: basicAuth, expires: 43200, created: Math.floor(Date.now() / 1000), admin: res.is_admin });
      })
  };
  const logout = () => {
    setUser(null)
  };
  const checkAuth = () => {
    if (user !== null) {
      // check if session has expired
      if (Math.floor(Date.now() / 1000) >= (user.created + user.expires)) {
        setUser(null);
        return false;
      } else {
        return true;
      }
    } else {
      return false;
    }
  };
  const getBasicAuth = () => {
    return user;
  };

  return (
    <AuthContext.Provider value={{ login, logout, checkAuth, getBasicAuth }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthProvider;