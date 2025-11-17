import type React from "react";
import {
  ActivityIcon,
  DatabaseIcon,
  GitBranchIcon,
  GlobeIcon,
  HomeIcon,
  SearchIcon,
  Settings2Icon,
} from "lucide-react";

export type NavigationItem = {
  title: string;
  href: string;
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  description: string;
};

export const ROUTES = {
  home: "/",
  browse: "/browse",
  search: "/search",
  activity: "/activity",
  repo: "/repo",
  data: "/data",
  settings: "/settings",
} as const;

export const NAV_ITEMS: NavigationItem[] = [
  {
    title: "Home",
    href: ROUTES.home,
    icon: HomeIcon,
    description: "Overview of your system and recent AI sessions",
  },
  {
    title: "Browse",
    href: ROUTES.browse,
    icon: GlobeIcon,
    description: "Browser shell with capture-aware tabs",
  },
  {
    title: "Search",
    href: ROUTES.search,
    icon: SearchIcon,
    description: "Search across tabs, memories, and indexed documents",
  },
  {
    title: "Activity",
    href: ROUTES.activity,
    icon: ActivityIcon,
    description: "Jobs, captures, and automations",
  },
  {
    title: "Repo",
    href: ROUTES.repo,
    icon: GitBranchIcon,
    description: "AI-assisted workflows for connected repositories",
  },
  {
    title: "Data",
    href: ROUTES.data,
    icon: DatabaseIcon,
    description: "Bundles, imports, and exports",
  },
  {
    title: "Settings",
    href: ROUTES.settings,
    icon: Settings2Icon,
    description: "LLM, capture, privacy, and retention settings",
  },
];

export const COMMAND_ACTIONS = [
  { id: "new-tab", label: "Open a new browser tab" },
  { id: "new-chat", label: "Start a fresh AI chat" },
  { id: "export-bundle", label: "Export a data bundle" },
  { id: "import-bundle", label: "Import a bundle" },
  { id: "run-repo-checks", label: "Run repo checks" },
  { id: "clear-history", label: "Clear current domain history" },
] as const;
