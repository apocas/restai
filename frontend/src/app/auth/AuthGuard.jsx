import { Navigate, useLocation } from "react-router-dom";

import useAuth from "app/hooks/useAuth";

export default function AuthGuard({ children }) {
  const { isAuthenticated } = useAuth();
  const { pathname } = useLocation();

  if (isAuthenticated) return <>{children}</>;

  return <Navigate replace to="/login" state={{ from: pathname }} />;
}
