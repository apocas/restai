import { authRoles } from "app/auth/authRoles";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import { useTranslation } from "react-i18next";

// Default navigations without conditional items
// Internal: the static nav tree. `nameKey`/`labelKey` are i18n keys; the
// `name`/`label` fallbacks are used when i18n is not yet initialized or
// a key is missing. `useNavigations()` below resolves the keys.
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
    path: "/admin/cron-logs",
    auth: authRoles.admin,
  },
  {
    name: "Permissions", nameKey: "nav.permissionMatrix",
    icon: "lock",
    path: "/admin/permissions",
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

// Pure function to build navigation structure based on gpu capability
// This doesn't use any hooks
export const buildNavigations = (hasGpu, hasProxy) => {
  const navigations = [...defaultNavigations.map(item => {
    // Deep clone the Generators item so we can modify its children
    if (item.name === "Generators") {
      return { ...item, children: [...item.children] };
    }
    return item;
  })];

  // The Image Gen and Audio Gen playgrounds are reachable from the
  // Image Generators / Speech-to-Text pages themselves (Playground
  // button), so they don't need dedicated nav entries.

  // Show AI Proxy after Tools when proxy is enabled
  if (hasProxy) {
    const toolsIndex = navigations.findIndex(item => item.path === "/projects/tools");
    navigations.splice(toolsIndex + 1, 0, {
      name: "AI Proxy", nameKey: "nav.aiProxy",
      icon: "route",
      path: "/proxy/keys",
      auth: authRoles.admin,
    });
  }

  return navigations;
};

// Walks the nav tree and swaps each `name`/`label` with its translated
// counterpart. Keeps other fields untouched so downstream renderers
// that read `item.icon`, `item.path`, etc. still work.
const translateNav = (items, t) =>
  items.map((item) => {
    const out = { ...item };
    if (item.nameKey)  out.name  = t(item.nameKey,  item.name);
    if (item.labelKey) out.label = t(item.labelKey, item.label);
    if (item.children) out.children = translateNav(item.children, t);
    return out;
  });

// Custom React hook that follows the rules of hooks
export const useNavigations = () => {
  const { platformCapabilities } = usePlatformCapabilities();
  const { t } = useTranslation();
  const hasGpu = platformCapabilities?.gpu ?? false;
  const hasProxy = platformCapabilities?.proxy ?? false;
  return translateNav(buildNavigations(hasGpu, hasProxy), t);
};

// For compatibility with direct imports (non-component files)
// This will not have dynamic GPU features but prevents errors
export const navigations = defaultNavigations;
