import { useState } from "react";
import { Box, Tab, Tabs } from "@mui/material";
import { List as ListIcon, Hub, QuestionAnswer } from "@mui/icons-material";
import { useTranslation } from "react-i18next";
import EntitiesPanel from "./knowledgegraph/EntitiesPanel";
import GraphPanel from "./knowledgegraph/GraphPanel";
import QueryPanel from "./knowledgegraph/QueryPanel";
import ContentCard from "app/components/page/ContentCard";
import { PALETTE } from "./forensic/styles";

export default function ProjectInfoKnowledgeGraph({ project }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState("entities");

  return (
    <ContentCard
      icon={<Hub />}
      title="Knowledge Graph"
      subtitle={`PROJECT/${String(project.id).padStart(4, "0")} · ENTITIES · GRAPH · QUERY`}
      sx={{ p: 0 }}
    >
      <Tabs
        value={tab}
        onChange={(e, v) => setTab(v)}
        sx={{ borderBottom: `1px solid ${PALETTE.edge}`, px: 2, mt: -1 }}
      >
        <Tab value="entities" icon={<ListIcon fontSize="small" />} iconPosition="start" label={t("projects.edit.knowledge.kgTabs.entities")} />
        <Tab value="graph" icon={<Hub fontSize="small" />} iconPosition="start" label={t("projects.edit.knowledge.kgTabs.graph")} />
        <Tab value="query" icon={<QuestionAnswer fontSize="small" />} iconPosition="start" label={t("projects.edit.knowledge.kgTabs.query")} />
      </Tabs>
      <Box sx={{ p: 3 }}>
        {tab === "entities" && <EntitiesPanel project={project} />}
        {tab === "graph" && <GraphPanel project={project} />}
        {tab === "query" && <QueryPanel project={project} />}
      </Box>
    </ContentCard>
  );
}
