import { lazy } from "react";
import Loadable from "app/components/Loadable";

const NotFound = Loadable(lazy(() => import("./NotFound")));
const JwtLogin = Loadable(lazy(() => import("./login/JwtLogin")));

const sessionRoutes = [
  { path: "/login", element: <JwtLogin /> },
  { path: "*", element: <NotFound /> }
];

export default sessionRoutes;
