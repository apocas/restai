import { authRoles } from "app/auth/authRoles";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

// Default navigations without conditional items
export const defaultNavigations = [
  { name: "Home", path: "/home", icon: "dashboard" },
  {
    name: "Library",
    icon: "library_books",
    path: "/projects/library",
  },
  { label: "AIaaS", type: "label" },
  {
    name: "Projects",
    icon: "assignment",
    path: "/projects",
  },
  {
    name: "Teams",
    icon: "groups",
    path: "/teams",
  },
  {
    name: "Users",
    icon: "person",
    path: "/users",
    auth: authRoles.admin,
  },
  { label: "AI", type: "label" },
  {
    name: "LLMs",
    icon: "psychology",
    path: "/llms",
  },
  {
    name: "Embeddings",
    icon: "psychology",
    path: "/embeddings",
  },
  {
    name: "Tools",
    icon: "build",
    path: "/projects/tools",
  },
  {
    name: "Classifiers",
    icon: "category",
    path: "/classifier",
  },
  {
    name: "Direct Access",
    icon: "api",
    path: "/direct",
  },
  {
    name: "Generators",
    icon: "memory",
    children: [
      { name: "GPU", iconText: "GP", path: "/gpu", auth: authRoles.admin },
    ]
  },
  { label: "Admin", type: "label", auth: authRoles.teamAdmin },
  {
    name: "Settings",
    icon: "settings",
    path: "/settings",
    auth: authRoles.admin,
  },
  {
    name: "Audit Log",
    icon: "history",
    path: "/audit",
    auth: authRoles.admin,
  },
  {
    name: "Cron Logs",
    icon: "schedule",
    path: "/admin/cron-logs",
    auth: authRoles.admin,
  },
  {
    name: "Permissions",
    icon: "lock",
    path: "/admin/permissions",
    auth: authRoles.teamAdmin,
  },
  { label: "Docs", type: "label" },
  {
    name: "Swagger",
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

  // Add Image Gen and Audio Gen to Generators when GPU is available
  if (hasGpu) {
    const generators = navigations.find(item => item.name === "Generators");
    if (generators) {
      generators.children.push(
        { name: "Image Gen", iconText: "IG", path: "/image" },
        { name: "Audio Gen", iconText: "AG", path: "/audio" }
      );
    }
  }

  // Show AI Proxy after Tools when proxy is enabled
  if (hasProxy) {
    const toolsIndex = navigations.findIndex(item => item.path === "/projects/tools");
    navigations.splice(toolsIndex + 1, 0, {
      name: "AI Proxy",
      icon: "route",
      path: "/proxy",
      auth: authRoles.admin,
      children: [
        { name: "API Keys", iconText: "SI", path: "/proxy/keys", auth: authRoles.admin },
        { name: "New Key", iconText: "SU", path: "/proxy/keys/new", auth: authRoles.admin },
      ]
    });
  }

  return navigations;
};

// Custom React hook that follows the rules of hooks
export const useNavigations = () => {
  const { platformCapabilities } = usePlatformCapabilities();
  const hasGpu = platformCapabilities?.gpu ?? false;
  const hasProxy = platformCapabilities?.proxy ?? false;
  return buildNavigations(hasGpu, hasProxy);
};

// For compatibility with direct imports (non-component files)
// This will not have dynamic GPU features but prevents errors
export const navigations = defaultNavigations;
