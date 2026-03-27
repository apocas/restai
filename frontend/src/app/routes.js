import { lazy } from "react";
import { Navigate } from "react-router-dom";

import AuthGuard from "./auth/AuthGuard";
import { authRoles } from "./auth/authRoles";

import Loadable from "./components/Loadable";
import MatxLayout from "./components/MatxLayout/MatxLayout";

import sessionRoutes from "./views/sessions/session-routes";

const Home = Loadable(lazy(() => import("app/views/dashboard/Home")));
const LLMs = Loadable(lazy(() => import("app/views/llms/List")));
const LLMsNew = Loadable(lazy(() => import("app/views/llms/NewInteractive")));
const LLMsInfo = Loadable(lazy(() => import("app/views/llms/Info")));
const LLMsEdit = Loadable(lazy(() => import("app/views/llms/Edit")));
const Embeddings = Loadable(lazy(() => import("app/views/embeddings/List")));
const EmbeddingsNew = Loadable(lazy(() => import("app/views/embeddings/NewInteractive")));
const EmbeddingsInfo = Loadable(lazy(() => import("app/views/embeddings/Info")));
const EmbeddingsEdit = Loadable(lazy(() => import("app/views/embeddings/Edit")));
const Projects = Loadable(lazy(() => import("app/views/projects/List")));
const MyProjects = Loadable(lazy(() => import("app/views/projects/MyList")));
const Library = Loadable(lazy(() => import("app/views/projects/Library")));
const Tools = Loadable(lazy(() => import("app/views/projects/Tools")));
const ProjectsInfo = Loadable(lazy(() => import("app/views/projects/Info")));
const ProjectsNew = Loadable(lazy(() => import("app/views/projects/New")));
const ProjectsEdit = Loadable(lazy(() => import("app/views/projects/Edit")));
const ProjectsLogs = Loadable(lazy(() => import("app/views/projects/Logs")));
const ProjectsPlayground = Loadable(lazy(() => import("app/views/projects/Playground")));
const ProjectsAPI = Loadable(lazy(() => import("app/views/projects/API")));
const ProjectsIDE = Loadable(lazy(() => import("app/views/projects/IDE")));
const ProjectsEvals = Loadable(lazy(() => import("app/views/projects/Evals")));
const Users = Loadable(lazy(() => import("app/views/users/List")));
const UsersInfo = Loadable(lazy(() => import("app/views/users/Info")));
const UsersNew = Loadable(lazy(() => import("app/views/users/New")));
const Image = Loadable(lazy(() => import("app/views/projects/Image")));
const Audio = Loadable(lazy(() => import("app/views/projects/Audio")));
const Keys = Loadable(lazy(() => import("app/views/proxy/Keys")));
const KeysNew = Loadable(lazy(() => import("app/views/proxy/New")));

// Team routes
const Teams = Loadable(lazy(() => import("app/views/teams/Teams")));
const TeamView = Loadable(lazy(() => import("app/views/teams/TeamView")));
const TeamEdit = Loadable(lazy(() => import("app/views/teams/TeamEdit")));
const DirectAccess = Loadable(lazy(() => import("app/views/direct/DirectAccess")));
const OllamaModels = Loadable(lazy(() => import("app/views/llms/ollama/OllamaModels")));
const Settings = Loadable(lazy(() => import("app/views/settings/Settings")));
const GpuInfo = Loadable(lazy(() => import("app/views/settings/GpuInfo")));

const routes = [
  {
    path: "/",
    element: <Navigate to="home" />
  },
  {
    element: (
      <AuthGuard>
        <MatxLayout />
      </AuthGuard>
    ),
    children: [
      {
        path: "/home",
        element: <Home />,
        auth: authRoles.admin
      },
      {
        path: "/users",
        element: <Users />,
        auth: authRoles.admin
      },
      {
        path: "/user/:id",
        element: <UsersInfo />,
        auth: authRoles.admin
      },
      {
        path: "/users/new",
        element: <UsersNew />,
        auth: authRoles.admin
      },
      {
        path: "/llms",
        element: <LLMs />,
        auth: authRoles.admin
      },
      {
        path: "/llms/new",
        element: <LLMsNew />,
        auth: authRoles.admin
      },
      {
        path: "/llms/ollama",
        element: <OllamaModels />,
        auth: authRoles.admin
      },
      {
        path: "/llm/:id",
        element: <LLMsInfo />,
        auth: authRoles.admin
      },
      {
        path: "/llm/:id/edit",
        element: <LLMsEdit />,
        auth: authRoles.admin
      },
      {
        path: "/embeddings",
        element: <Embeddings />,
        auth: authRoles.admin
      },
      {
        path: "/embeddings/new",
        element: <EmbeddingsNew />,
        auth: authRoles.admin
      },
      {
        path: "/embedding/:id",
        element: <EmbeddingsInfo />,
        auth: authRoles.admin
      },
      {
        path: "/embedding/:id/edit",
        element: <EmbeddingsEdit />,
        auth: authRoles.admin
      },
      {
        path: "/projects",
        element: <Projects />,
        auth: authRoles.admin
      },
      {
        path: "/projects/my",
        element: <MyProjects />,
        auth: authRoles.admin
      },
      {
        path: "/projects/library",
        element: <Library />,
        auth: authRoles.admin
      },
      {
        path: "/projects/tools",
        element: <Tools />,
        auth: authRoles.admin
      },
      {
        path: "/project/:id",
        element: <ProjectsInfo />,
        auth: authRoles.admin
      },
      {
        path: "/projects/new",
        element: <ProjectsNew />,
        auth: authRoles.admin
      },
      {
        path: "/project/:id/edit",
        element: <ProjectsEdit />,
        auth: authRoles.admin
      },
      {
        path: "/project/:id/logs",
        element: <ProjectsLogs />,
        auth: authRoles.admin
      },
      {
        path: "/project/:id/playground",
        element: <ProjectsPlayground />,
        auth: authRoles.admin
      },
      {
        path: "/project/:id/api",
        element: <ProjectsAPI />,
        auth: authRoles.admin
      },
      {
        path: "/project/:id/ide",
        element: <ProjectsIDE />,
        auth: authRoles.admin
      },
      {
        path: "/project/:id/evals",
        element: <ProjectsEvals />,
        auth: authRoles.admin
      },
      {
        path: "/proxy/keys",
        element: <Keys />,
        auth: authRoles.admin
      },
      {
        path: "/proxy/keys/new",
        element: <KeysNew />,
        auth: authRoles.admin
      },
      {
        path: "/image",
        element: <Image />,
        auth: authRoles.admin
      },
      {
        path: "/audio",
        element: <Audio />,
        auth: authRoles.admin
      },
      {
        path: "/teams",
        element: <Teams />,
        auth: authRoles.admin
      },
      {
        path: "/teams/new",
        element: <TeamEdit />,
        auth: authRoles.admin
      },
      {
        path: "/team/:id",
        element: <TeamView />,
        auth: authRoles.admin
      },
      {
        path: "/team/:id/edit",
        element: <TeamEdit />,
        auth: authRoles.admin
      },
      {
        path: "/direct",
        element: <DirectAccess />,
        auth: authRoles.admin
      },
      {
        path: "/settings",
        element: <Settings />,
        auth: authRoles.admin
      },
      {
        path: "/gpu",
        element: <GpuInfo />,
        auth: authRoles.admin
      }
    ]
  },

  ...sessionRoutes
];

export default routes;
