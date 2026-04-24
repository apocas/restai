import { useState } from "react";
import { Box, Card, Tab, Tabs } from "@mui/material";
import { List as ListIcon, Hub, QuestionAnswer } from "@mui/icons-material";
import { useTranslation } from "react-i18next";
import EntitiesPanel from "./knowledgegraph/EntitiesPanel";
import GraphPanel from "./knowledgegraph/GraphPanel";
import QueryPanel from "./knowledgegraph/QueryPanel";

export default function ProjectInfoKnowledgeGraph({ project }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState("entities");

  return (
    <Card elevation={1} sx={{ p: 0, borderRadius: 3, overflow: "hidden" }}>
      <Tabs
        value={tab}
        onChange={(e, v) => setTab(v)}
        sx={{ borderBottom: 1, borderColor: "divider", px: 2 }}
      >
        <Tab value="entities" icon={<ListIcon fontSize="small" />} iconPosition="start" label={t("projects.knowledge.kgTabs.entities")} />
        <Tab value="graph" icon={<Hub fontSize="small" />} iconPosition="start" label={t("projects.knowledge.kgTabs.graph")} />
        <Tab value="query" icon={<QuestionAnswer fontSize="small" />} iconPosition="start" label={t("projects.knowledge.kgTabs.query")} />
      </Tabs>
      <Box sx={{ p: 3 }}>
        {tab === "entities" && <EntitiesPanel project={project} />}
        {tab === "graph" && <GraphPanel project={project} />}
        {tab === "query" && <QueryPanel project={project} />}
      </Box>
    </Card>
  );
}
