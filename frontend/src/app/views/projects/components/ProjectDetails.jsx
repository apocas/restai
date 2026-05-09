import { useState } from "react";
import { Fade, Grid } from "@mui/material";
import { Info, Storage, Shield, BarChart, ChatBubble, Widgets, Hub, Build, Schedule, PhoneAndroid, VpnKey, Memory, TravelExplore } from "@mui/icons-material";

import ProjectInfo from "./ProjectInfo";
import ProjectTabNav from "./ProjectTabNav";
import ProjectInfoGeneral from "./ProjectInfoGeneral";
import ProjectInfoKnowledge from "./ProjectInfoKnowledge";
import ProjectInfoKnowledgeGraph from "./ProjectInfoKnowledgeGraph";
import ProjectInfoSecurity from "./ProjectInfoSecurity";
import ProjectInfoAnalytics from "./ProjectInfoAnalytics";
import ProjectComments from "./ProjectComments";
import ProjectWidget from "./ProjectWidget";
import ProjectInfoTools from "./ProjectInfoTools";
import ProjectEditRoutines from "./ProjectEditRoutines";
import ProjectEditMobile from "./ProjectEditMobile";
import ProjectEditSecrets from "./ProjectEditSecrets";
import ProjectEditMemoryBank from "./ProjectEditMemoryBank";
import ProjectEditMemorySearch from "./ProjectEditMemorySearch";

const ALL_TABS = [
  // Section: Build — what the project is and its content
  { name: "General",         Icon: Info,          section: "build" },
  { name: "Knowledge",       Icon: Storage,       section: "build", ragOnly: true },
  { name: "Knowledge Graph", Icon: Hub,           section: "build", ragOnly: true, kgOnly: true },
  { name: "Tools",           Icon: Build,         section: "build", agentOnly: true },
  { name: "Secrets",         Icon: VpnKey,        section: "build", agentOnly: true },
  { name: "Memory Bank",     Icon: Memory,        section: "build", memoryBankOnly: true },
  { name: "Memory",          Icon: TravelExplore, section: "build", memorySearchOnly: true },
  // Section: Operate — automation, safety, observability
  { name: "Routines",        Icon: Schedule,      section: "operate" },
  { name: "Security",        Icon: Shield,        section: "operate" },
  { name: "Analytics",       Icon: BarChart,      section: "operate" },
  // Section: Engage — user-facing surfaces
  { name: "Widget",          Icon: Widgets,       section: "engage" },
  { name: "Mobile",          Icon: PhoneAndroid,  section: "engage" },
  { name: "Comments",        Icon: ChatBubble,    section: "engage" },
];

export default function ProjectDetails({ project, projects, info }) {
  const [active, setActive] = useState("General");

  const tabs = ALL_TABS.filter((t) => {
    if (t.ragOnly && project.type !== "rag") return false;
    if (t.kgOnly && !project.options?.enable_knowledge_graph) return false;
    if (t.agentOnly && project.type !== "agent") return false;
    if (t.memoryBankOnly && !project.options?.memory_bank_enabled) return false;
    if (t.memorySearchOnly && !project.options?.memory_search_enabled) return false;
    return true;
  });

  return (
    <Fade in timeout={300}>
      <div>
        {/* Hero header — always visible */}
        <ProjectInfo project={project} projects={projects} info={info} />

        {/* Tabbed content */}
        <Grid container spacing={3}>
          <Grid item md={2} xs={12}>
            <ProjectTabNav tabs={tabs} active={active} setActive={setActive} />
          </Grid>

          <Grid item md={10} xs={12}>
            {active === "General" && <ProjectInfoGeneral project={project} info={info} />}
            {active === "Knowledge" && <ProjectInfoKnowledge project={project} />}
            {active === "Knowledge Graph" && <ProjectInfoKnowledgeGraph project={project} />}
            {active === "Tools" && <ProjectInfoTools project={project} />}
            {active === "Secrets" && <ProjectEditSecrets project={project} />}
            {active === "Memory Bank" && <ProjectEditMemoryBank project={project} />}
            {active === "Memory" && <ProjectEditMemorySearch project={project} />}
            {active === "Routines" && <ProjectEditRoutines project={project} />}
            {active === "Security" && <ProjectInfoSecurity project={project} />}
            {active === "Analytics" && <ProjectInfoAnalytics project={project} />}
            {active === "Widget" && <ProjectWidget project={project} />}
            {active === "Mobile" && <ProjectEditMobile project={project} />}
            {active === "Comments" && <ProjectComments project={project} />}
          </Grid>
        </Grid>
      </div>
    </Fade>
  );
}
