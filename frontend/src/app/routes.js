import { lazy } from "react";
import { Navigate } from "react-router-dom";

import AuthGuard from "./auth/AuthGuard";
import { authRoles } from "./auth/authRoles";

import Loadable from "./components/Loadable";
import MatxLayout from "./components/MatxLayout/MatxLayout";

import sessionRoutes from "./views/sessions/session-routes";

const Home = Loadable(lazy(() => import("app/views/dashboard/Home")));
const LLMs = Loadable(lazy(() => import("app/views/llms/List")));
const LLMsNewChooser = Loadable(lazy(() => import("app/views/llms/NewChooser")));
const LLMsNew = Loadable(lazy(() => import("app/views/llms/NewInteractive")));
const LLMsInfo = Loadable(lazy(() => import("app/views/llms/Info")));
const LLMsEdit = Loadable(lazy(() => import("app/views/llms/Edit")));
const Embeddings = Loadable(lazy(() => import("app/views/embeddings/List")));
const ImageGenerators = Loadable(lazy(() => import("app/views/image_generators/List")));
const SpeechToText = Loadable(lazy(() => import("app/views/speech_to_text/List")));
const EmbeddingsNewChooser = Loadable(lazy(() => import("app/views/embeddings/NewChooser")));
const EmbeddingsNew = Loadable(lazy(() => import("app/views/embeddings/NewInteractive")));
const EmbeddingsInfo = Loadable(lazy(() => import("app/views/embeddings/Info")));
const EmbeddingsEdit = Loadable(lazy(() => import("app/views/embeddings/Edit")));
const Projects = Loadable(lazy(() => import("app/views/projects/List")));
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
const ProjectsGuards = Loadable(lazy(() => import("app/views/projects/Guards")));
const Users = Loadable(lazy(() => import("app/views/users/List")));
const UsersInfo = Loadable(lazy(() => import("app/views/users/Info")));
const UsersNew = Loadable(lazy(() => import("app/views/users/New")));
const Image = Loadable(lazy(() => import("app/views/projects/Image")));
const Audio = Loadable(lazy(() => import("app/views/projects/Audio")));
const Keys = Loadable(lazy(() => import("app/views/proxy/Keys")));

// Team routes
const Teams = Loadable(lazy(() => import("app/views/teams/Teams")));
const TeamView = Loadable(lazy(() => import("app/views/teams/TeamView")));
const TeamEdit = Loadable(lazy(() => import("app/views/teams/TeamEdit")));
const DirectAccess = Loadable(lazy(() => import("app/views/direct/DirectAccess")));
const ClassifierPlayground = Loadable(lazy(() => import("app/views/classifier/ClassifierPlayground")));
const PermissionMatrix = Loadable(lazy(() => import("app/views/admin/PermissionMatrix")));
const OllamaModels = Loadable(lazy(() => import("app/views/llms/ollama/OllamaModels")));
const Settings = Loadable(lazy(() => import("app/views/settings/Settings")));
const GpuInfo = Loadable(lazy(() => import("app/views/settings/GpuInfo")));
const AuditLog = Loadable(lazy(() => import("app/views/audit/AuditLog")));
const CronLogs = Loadable(lazy(() => import("app/views/admin/CronLogs")));
const InvitationsPage = Loadable(lazy(() => import("app/views/invitations/Invitations")));

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
        auth: authRoles.user
      },
      {
        path: "/llms/new",
        element: <LLMsNewChooser />,
        auth: authRoles.admin
      },
      {
        path: "/llms/new/manual",
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
        auth: authRoles.user
      },
      {
        path: "/llm/:id/edit",
        element: <LLMsEdit />,
        auth: authRoles.admin
      },
      {
        path: "/embeddings",
        element: <Embeddings />,
        auth: authRoles.user
      },
      {
        path: "/embeddings/new",
        element: <EmbeddingsNewChooser />,
        auth: authRoles.admin
      },
      {
        path: "/embeddings/new/manual",
        element: <EmbeddingsNew />,
        auth: authRoles.admin
      },
      {
        path: "/embedding/:id",
        element: <EmbeddingsInfo />,
        auth: authRoles.user
      },
      {
        path: "/embedding/:id/edit",
        element: <EmbeddingsEdit />,
        auth: authRoles.admin
      },
      {
        path: "/image_generators",
        element: <ImageGenerators />,
        auth: authRoles.user
      },
      {
        path: "/speech_to_text",
        element: <SpeechToText />,
        auth: authRoles.user
      },
      {
        path: "/projects",
        element: <Projects />,
        auth: authRoles.user
      },
      {
        path: "/projects/library",
        element: <Library />,
        auth: authRoles.user
      },
      {
        path: "/projects/tools",
        element: <Tools />,
        auth: authRoles.user
      },
      {
        path: "/project/:id",
        element: <ProjectsInfo />,
        auth: authRoles.user
      },
      {
        path: "/projects/new",
        element: <ProjectsNew />,
        auth: authRoles.user
      },
      {
        path: "/project/:id/edit",
        element: <ProjectsEdit />,
        auth: authRoles.user
      },
      {
        path: "/project/:id/logs",
        element: <ProjectsLogs />,
        auth: authRoles.user
      },
      {
        path: "/project/:id/playground",
        element: <ProjectsPlayground />,
        auth: authRoles.user
      },
      {
        path: "/project/:id/api",
        element: <ProjectsAPI />,
        auth: authRoles.user
      },
      {
        path: "/project/:id/ide",
        element: <ProjectsIDE />,
        auth: authRoles.user
      },
      {
        path: "/project/:id/evals",
        element: <ProjectsEvals />,
        auth: authRoles.user
      },
      {
        path: "/project/:id/guards",
        element: <ProjectsGuards />,
        auth: authRoles.user
      },
      {
        path: "/proxy/keys",
        element: <Keys />,
        auth: authRoles.admin
      },
      {
        path: "/classifier",
        element: <ClassifierPlayground />,
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
      },
      {
        path: "/audit",
        element: <AuditLog />,
        auth: authRoles.admin
      },
      {
        path: "/admin/cron-logs",
        element: <CronLogs />,
        auth: authRoles.admin
      },
      {
        path: "/admin/permissions",
        element: <PermissionMatrix />,
        auth: authRoles.teamAdmin
      },
      {
        path: "/invitations",
        element: <InvitationsPage />,
        auth: authRoles.user
      }
    ]
  },

  ...sessionRoutes
];

export default routes;
