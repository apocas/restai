import { authRoles } from "app/auth/authRoles";
import { useTranslation } from "react-i18next";

// `nameKey`/`labelKey` are i18n keys; `name`/`label` are fallbacks used before
// i18n initializes or when a key is missing.
export const defaultNavigations = [
  { name: "Home", nameKey: "nav.home", path: "/home", icon: "dashboard" },
  {
    name: "Library", nameKey: "nav.library",
    icon: "library_books",
    path: "/projects/library",
  },
  { label: "AIaaS", type: "label" },
  {
    name: "Projects", nameKey: "nav.projects",
    icon: "assignment",
    path: "/projects",
  },
  {
    name: "Teams", nameKey: "nav.teams",
    icon: "groups",
    path: "/teams",
  },
  {
    name: "Users", nameKey: "nav.users",
    icon: "person",
    path: "/users",
    auth: authRoles.admin,
  },
  { label: "AI", type: "label" },
  {
    name: "LLMs", nameKey: "nav.llms",
    icon: "psychology",
    path: "/llms",
  },
  {
    name: "Embeddings", nameKey: "nav.embeddings",
    icon: "psychology",
    path: "/embeddings",
  },
  {
    name: "Tools", nameKey: "nav.tools",
    icon: "build",
    path: "/projects/tools",
  },
  {
    name: "Classifiers", nameKey: "nav.classifiers",
    icon: "category",
    path: "/classifier",
  },
  {
    name: "Direct Access", nameKey: "nav.directAccess",
    icon: "api",
    path: "/direct",
  },
  {
    name: "Generators", nameKey: "nav.generators",
    icon: "memory",
    children: [
      { name: "Image Generators", nameKey: "nav.imageGenerators", iconText: "IG", path: "/generators/image" },
      { name: "Speech-to-Text",   nameKey: "nav.speechToText",    iconText: "ST", path: "/generators/speech2text" },
      { name: "GPU", nameKey: "nav.gpu", iconText: "GP", path: "/gpu", auth: authRoles.admin },
    ]
  },
  { label: "Admin", labelKey: "nav.adminLabel", type: "label", auth: authRoles.teamAdmin },
  {
    name: "Settings", nameKey: "nav.settings",
    icon: "settings",
    path: "/settings",
    auth: authRoles.admin,
  },
  {
    name: "Audit Log", nameKey: "nav.auditLog",
    icon: "history",
    path: "/audit",
    auth: authRoles.admin,
  },
  {
    name: "Cron Logs", nameKey: "nav.cronLogs",
    icon: "schedule",
    path: "/cron-logs",
    auth: authRoles.admin,
  },
  {
    name: "Routines", nameKey: "nav.routines",
    icon: "alarm",
    path: "/routines",
    auth: authRoles.admin,
  },
  {
    name: "Permissions", nameKey: "nav.permissionMatrix",
    icon: "lock",
    path: "/permissions",
    auth: authRoles.teamAdmin,
  },
  { label: "Docs", labelKey: "nav.docsLabel", type: "label" },
  {
    name: "Swagger", nameKey: "nav.swagger",
    icon: "launch",
    type: "extLink",
    path: "/docs/"
  }
];

// Hook-free so direct imports work; useNavigations() wraps this.
export const buildNavigations = () => {
  const navigations = [...defaultNavigations.map(item => {
    // Deep clone Generators so we can mutate its children.
    if (item.name === "Generators") {
      return { ...item, children: [...item.children] };
    }
    return item;
  })];

  return navigations;
};

const translateNav = (items, t) =>
  items.map((item) => {
    const out = { ...item };
    if (item.nameKey)  out.name  = t(item.nameKey,  item.name);
    if (item.labelKey) out.label = t(item.labelKey, item.label);
    if (item.children) out.children = translateNav(item.children, t);
    return out;
  });

export const useNavigations = () => {
  const { t } = useTranslation();
  return translateNav(buildNavigations(), t);
};

// For direct imports (non-component files). No dynamic GPU features.
export const navigations = defaultNavigations;
