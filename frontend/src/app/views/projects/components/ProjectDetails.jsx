import { useState } from "react";
import { Fade, Grid } from "@mui/material";
import { Info, Storage, Shield, BarChart, ChatBubble, Widgets, Hub } from "@mui/icons-material";

import ProjectInfo from "./ProjectInfo";
import ProjectTabNav from "./ProjectTabNav";
import ProjectInfoGeneral from "./ProjectInfoGeneral";
import ProjectInfoKnowledge from "./ProjectInfoKnowledge";
import ProjectInfoKnowledgeGraph from "./ProjectInfoKnowledgeGraph";
import ProjectInfoSecurity from "./ProjectInfoSecurity";
import ProjectInfoAnalytics from "./ProjectInfoAnalytics";
import ProjectComments from "./ProjectComments";
import ProjectWidget from "./ProjectWidget";

const ALL_TABS = [
  { name: "General", Icon: Info },
  { name: "Knowledge", Icon: Storage, ragOnly: true },
  { name: "Knowledge Graph", Icon: Hub, ragOnly: true, kgOnly: true },
  { name: "Security", Icon: Shield },
  { name: "Analytics", Icon: BarChart },
  { name: "Widget", Icon: Widgets },
  { name: "Comments", Icon: ChatBubble },
];

export default function ProjectDetails({ project, projects, info }) {
  const [active, setActive] = useState("General");

  const tabs = ALL_TABS.filter((t) => {
    if (t.ragOnly && project.type !== "rag") return false;
    if (t.kgOnly && !project.options?.enable_knowledge_graph) return false;
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
            {active === "Security" && <ProjectInfoSecurity project={project} />}
            {active === "Analytics" && <ProjectInfoAnalytics project={project} />}
            {active === "Widget" && <ProjectWidget project={project} />}
            {active === "Comments" && <ProjectComments project={project} />}
          </Grid>
        </Grid>
      </div>
    </Fade>
  );
}
