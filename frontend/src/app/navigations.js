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
    children: [
      { name: "My Projects", iconText: "SI", path: "/projects/my" },
      { name: "List Projects", iconText: "SI", path: "/projects" },
      { name: "New Project", iconText: "SU", path: "/projects/new" },
    ]
  },
  {
    name: "Teams",
    icon: "groups",
    path: "/teams",
    children: [
      { name: "Team List", iconText: "TL", path: "/teams" },
      { name: "New Team", iconText: "NT", path: "/teams/new", auth: authRoles.admin },
    ]
  },
  {
    name: "Users",
    icon: "person",
    path: "/users",
    auth: authRoles.admin,
    children: [
      { name: "User List", iconText: "SI", path: "/users", auth: authRoles.admin },
      { name: "New User", iconText: "SU", path: "/users/new", auth: authRoles.admin },
    ]
  },
  { label: "AI", type: "label" },
  {
    name: "LLMs",
    icon: "psychology",
    path: "/llms",
    children: [
      { name: "List LLMs", iconText: "SI", path: "/llms" },
      { name: "New LLM", iconText: "SU", path: "/llms/new", auth: authRoles.admin },
    ]
  },
  {
    name: "Embeddings",
    icon: "psychology",
    path: "/embeddings",
    children: [
      { name: "List Embeddings", iconText: "SI", path: "/embeddings" },
      { name: "New Embedding", iconText: "SU", path: "/embeddings/new", auth: authRoles.admin },
    ]
  },
  {
    name: "Import from Ollama",
    icon: "cloud_download",
    path: "/llms/ollama",
    auth: authRoles.admin,
  },
  {
    name: "Tools",
    icon: "build",
    path: "/projects/tools",
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
  { label: "Admin", type: "label" },
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
