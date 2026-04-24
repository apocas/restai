import { useState, useEffect, Fragment } from "react";
import {
  Box,
  Grid,
  styled,
  Card,
  Typography,
  Button,
  Tabs,
  Tab,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Avatar,
  Divider,
  IconButton,
  Tooltip,
  CircularProgress,
  LinearProgress
} from "@mui/material";
import TableRow from '@mui/material/TableRow';
import TableCell from '@mui/material/TableCell';
import { useNavigate, useParams } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import { Breadcrumb } from "app/components";
import { toast } from 'react-toastify';
import { useTranslation } from "react-i18next";
import { Person, Settings, Delete, Group, Code, Psychology, AccountBalanceWallet, Receipt, AllInclusive, Image, Speaker } from "@mui/icons-material";
import MUIDataTable from "mui-datatables";
import ReactJson from '@microlink/react-json-view';
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" },
  "& .breadcrumb": {
    marginBottom: "30px",
    [theme.breakpoints.down("sm")]: { marginBottom: "16px" }
  }
}));

const StyledCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(3),
  marginBottom: theme.spacing(3)
}));

function TabPanel(props) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`team-tabpanel-${index}`}
      aria-labelledby={`team-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

export default function TeamView() {
  const { t } = useTranslation();
  const { id } = useParams();
  const [team, setTeam] = useState(null);
  const [tabValue, setTabValue] = useState(0);
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);

  const [transactions, setTransactions] = useState([]);
  const [txPage, setTxPage] = useState(0);
  const [txRows, setTxRows] = useState(100);
  const [txCount, setTxCount] = useState(0);
  const [txLog, setTxLog] = useState({});
  const [txRowsExpanded, setTxRowsExpanded] = useState([]);
  const [txLoaded, setTxLoaded] = useState(false);

  const isTeamAdmin = team?.admins?.some(admin => admin.id === user.id) || user.is_admin;

  const fetchTeam = async () => {
    setLoading(true);
    try {
      const data = await api.get(`/teams/${id}`, user.token);
      setTeam(data);
    } catch (error) {
      // errors auto-toasted
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTeam();
  }, [id]);

  useEffect(() => {
    if (team) {
      document.title = `${process.env.REACT_APP_RESTAI_NAME || "RESTai"} - Team: ${team.name}`;
    }
  }, [team]);

  const fetchTransactions = async () => {
    const txStart = txPage * txRows;
    const txEnd = txStart + txRows;
    try {
      const data = await api.get(`/teams/${id}/transactions?start=${txStart}&end=${txEnd}`, user.token);
      if (data.transactions) {
        setTransactions(data.transactions);
        setTxCount(data.total);
      }
    } catch (error) {
      // errors auto-toasted
    }
  };

  useEffect(() => {
    if (tabValue === 3 && team) {
      fetchTransactions();
      setTxLoaded(true);
    }
  }, [tabValue, team, txPage, txRows]);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const handleEditTeam = () => {
    navigate(`/team/${id}/edit`);
  };

  const handleRemoveUser = async (username) => {
    if (!window.confirm(t("teams.view.confirmRemove", { name: username }))) {
      return;
    }

    try {
      await api.delete(`/teams/${id}/users/${username}`, user.token);
      toast.success(t("teams.view.removed", { name: username }));
      fetchTeam();
    } catch (error) {
      // errors auto-toasted
    }
  };

  const handleRemoveAdmin = async (username) => {
    if (!window.confirm(t("teams.view.confirmRemoveAdmin", { name: username }))) {
      return;
    }

    try {
      await api.delete(`/teams/${id}/admins/${username}`, user.token);
      toast.success(t("teams.view.adminRemoved", { name: username }));
      fetchTeam();
    } catch (error) {
      // errors auto-toasted
    }
  };

  const handleRemoveProject = async (projectId) => {
    if (!window.confirm(t("teams.view.confirmRemoveProject"))) {
      return;
    }

    try {
      await api.delete(`/teams/${id}/projects/${projectId}`, user.token);
      toast.success(t("teams.view.projectRemoved"));
      fetchTeam();
    } catch (error) {
      // errors auto-toasted
    }
  };

  const handleRemoveLLM = async (llm) => {
    if (!window.confirm(t("teams.view.confirmRemove", { name: llm.name }))) {
      return;
    }

    try {
      await api.delete(`/teams/${id}/llms/${llm.id}`, user.token);
      toast.success(t("teams.view.removed", { name: llm.name }));
      fetchTeam();
    } catch (error) {
      // errors auto-toasted
    }
  };

  const handleRemoveEmbedding = async (embedding) => {
    if (!window.confirm(t("teams.view.confirmRemove", { name: embedding.name }))) {
      return;
    }

    try {
      await api.delete(`/teams/${id}/embeddings/${embedding.id}`, user.token);
      toast.success(t("teams.view.removed", { name: embedding.name }));
      fetchTeam();
    } catch (error) {
      // errors auto-toasted
    }
  };

  const handleRemoveImageGenerator = async (generatorName) => {
    if (!window.confirm(t("teams.view.confirmRemove", { name: generatorName }))) {
      return;
    }

    try {
      await api.delete(`/teams/${id}/image_generators/${generatorName}`, user.token);
      toast.success(t("teams.view.removed", { name: generatorName }));
      fetchTeam();
    } catch (error) {
      // errors auto-toasted
    }
  };

  const handleRemoveAudioGenerator = async (generatorName) => {
    if (!window.confirm(t("teams.view.confirmRemove", { name: generatorName }))) {
      return;
    }

    try {
      await api.delete(`/teams/${id}/audio_generators/${generatorName}`, user.token);
      toast.success(t("teams.view.removed", { name: generatorName }));
      fetchTeam();
    } catch (error) {
      // errors auto-toasted
    }
  };

  if (loading) {
    return (
      <Container>
        <Box className="breadcrumb">
          <Breadcrumb routeSegments={[
            { name: t("nav.teams"), path: "/teams" },
            { name: t("common.loading"), path: `/teams/${id}` }
          ]} />
        </Box>
        <Typography>{t("teams.view.loading")}</Typography>
      </Container>
    );
  }

  if (!team) {
    return (
      <Container>
        <Box className="breadcrumb">
          <Breadcrumb routeSegments={[
            { name: t("nav.teams"), path: "/teams" },
            { name: t("teams.view.notFoundTitle"), path: `/teams/${id}` }
          ]} />
        </Box>
        <Typography>{t("teams.view.notFound")}</Typography>
      </Container>
    );
  }

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[
          { name: t("nav.teams"), path: "/teams" },
          { name: team.name, path: `/teams/${id}` }
        ]} />
      </Box>

      <StyledCard>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Box>
            <Typography variant="h4">{team.name}</Typography>
            <Typography variant="body1" color="textSecondary">
              {team.description || t("teams.view.noDescription")}
            </Typography>
            {team.budget >= 0 ? (() => {
              const spent = team.spending ?? 0;
              const budget = team.budget;
              const pct = budget > 0 ? Math.min((spent / budget) * 100, 100) : 0;
              const barColor = pct > 90 ? "error" : pct > 70 ? "warning" : "primary";
              return (
                <Box mt={1.5} maxWidth={400}>
                  <Box display="flex" justifyContent="space-between" mb={0.5}>
                    <Box display="flex" alignItems="center" gap={0.5}>
                      <AccountBalanceWallet sx={{ fontSize: 16, color: "text.secondary" }} />
                      <Typography variant="caption" color="text.secondary" fontWeight={600}>
                        {t("teams.view.spent")} ${spent.toFixed(2)} / ${budget.toFixed(2)}
                      </Typography>
                    </Box>
                    <Typography variant="caption" color="text.secondary" fontWeight={600}>
                      ${(team.remaining ?? 0).toFixed(2)} {t("teams.view.left")}
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={pct}
                    color={barColor}
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </Box>
              );
            })() : (
              <Box display="flex" alignItems="center" gap={0.5} mt={1}>
                <AllInclusive sx={{ fontSize: 16, color: "text.disabled" }} />
                <Typography variant="caption" color="text.disabled" fontWeight={600}>
                  {t("teams.view.unlimited")}
                </Typography>
              </Box>
            )}
          </Box>
          {isTeamAdmin && (
            <Button
              variant="contained"
              color="primary"
              startIcon={<Settings />}
              onClick={handleEditTeam}
            >
              {t("teams.view.edit")}
            </Button>
          )}
        </Box>
        
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={tabValue} onChange={handleTabChange} aria-label="team tabs">
            <Tab label={t("teams.edit.tabs.users")} icon={<Group />} iconPosition="start" />
            <Tab label={t("teams.edit.tabs.projects")} icon={<Code />} iconPosition="start" />
            <Tab label={t("teams.edit.tabs.models")} icon={<Psychology />} iconPosition="start" />
            {isTeamAdmin && (
              <Tab label={t("teams.view.tabs.transactions")} icon={<Receipt />} iconPosition="start" />
            )}
          </Tabs>
        </Box>
        
        <TabPanel value={tabValue} index={0}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>{t("teams.edit.members")}</Typography>
              <List>
                {team.users?.length > 0 ? (
                  team.users.map((member) => (
                    <Fragment key={member.id}>
                      <ListItem secondaryAction={
                        isTeamAdmin && (
                          <Tooltip title={t("teams.view.removeUser")}>
                            <IconButton edge="end" onClick={() => handleRemoveUser(member.username)}>
                              <Delete />
                            </IconButton>
                          </Tooltip>
                        )
                      }>
                        <ListItemAvatar>
                          <Avatar>
                            <Person />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText primary={member.username} />
                      </ListItem>
                      <Divider variant="inset" component="li" />
                    </Fragment>
                  ))
                ) : (
                  <Typography variant="body2" color="textSecondary">{t("teams.view.noMembers")}</Typography>
                )}
              </List>
            </Grid>
            
            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>{t("teams.edit.admins")}</Typography>
              <List>
                {team.admins?.length > 0 ? (
                  team.admins.map((admin) => (
                    <Fragment key={admin.id}>
                      <ListItem secondaryAction={
                        isTeamAdmin && (
                          <Tooltip title={t("teams.view.removeAdmin")}>
                            <IconButton edge="end" onClick={() => handleRemoveAdmin(admin.username)}>
                              <Delete />
                            </IconButton>
                          </Tooltip>
                        )
                      }>
                        <ListItemAvatar>
                          <Avatar>
                            <Person />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText 
                          primary={admin.username} 
                          secondary={admin.id === user.id ? t("teams.view.you") : ""}
                        />
                      </ListItem>
                      <Divider variant="inset" component="li" />
                    </Fragment>
                  ))
                ) : (
                  <Typography variant="body2" color="textSecondary">{t("teams.view.noAdmins")}</Typography>
                )}
              </List>
            </Grid>
          </Grid>
        </TabPanel>
        
        <TabPanel value={tabValue} index={1}>
          <Typography variant="h6" gutterBottom>{t("teams.edit.projectsHeading")}</Typography>
          <List>
            {team.projects?.length > 0 ? (
              team.projects.map((project) => (
                <Fragment key={project.id}>
                  <ListItem 
                    button
                    onClick={() => navigate(`/project/${project.id}`)}
                    secondaryAction={
                      isTeamAdmin && (
                        <Tooltip title={t("teams.view.removeProject")}>
                          <IconButton edge="end" onClick={(e) => {
                            e.stopPropagation();
                            handleRemoveProject(project.id);
                          }}>
                            <Delete />
                          </IconButton>
                        </Tooltip>
                      )
                    }
                  >
                    <ListItemAvatar>
                      <Avatar>
                        <Code />
                      </Avatar>
                    </ListItemAvatar>
                    <ListItemText primary={project.name} />
                  </ListItem>
                  <Divider variant="inset" component="li" />
                </Fragment>
              ))
            ) : (
              <Typography variant="body2" color="textSecondary">{t("teams.view.noProjects")}</Typography>
            )}
          </List>
        </TabPanel>
        
        <TabPanel value={tabValue} index={2}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>{t("teams.edit.llms")}</Typography>
              <List>
                {team.llms?.length > 0 ? (
                  team.llms.map((llm) => (
                    <Fragment key={llm.id}>
                      <ListItem secondaryAction={
                        isTeamAdmin && (
                          <Tooltip title={t("teams.view.removeLlm")}>
                            <IconButton edge="end" onClick={() => handleRemoveLLM(llm)}>
                              <Delete />
                            </IconButton>
                          </Tooltip>
                        )
                      }>
                        <ListItemAvatar>
                          <Avatar>
                            <Psychology />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText primary={llm.name} />
                      </ListItem>
                      <Divider variant="inset" component="li" />
                    </Fragment>
                  ))
                ) : (
                  <Typography variant="body2" color="textSecondary">{t("teams.view.noLlms")}</Typography>
                )}
              </List>
            </Grid>
            
            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>{t("teams.edit.embeddings")}</Typography>
              <List>
                {team.embeddings?.length > 0 ? (
                  team.embeddings.map((embedding) => (
                    <Fragment key={embedding.id}>
                      <ListItem secondaryAction={
                        isTeamAdmin && (
                          <Tooltip title={t("teams.view.removeEmbedding")}>
                            <IconButton edge="end" onClick={() => handleRemoveEmbedding(embedding)}>
                              <Delete />
                            </IconButton>
                          </Tooltip>
                        )
                      }>
                        <ListItemAvatar>
                          <Avatar>
                            <Psychology />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText primary={embedding.name} />
                      </ListItem>
                      <Divider variant="inset" component="li" />
                    </Fragment>
                  ))
                ) : (
                  <Typography variant="body2" color="textSecondary">{t("teams.view.noEmbeddings")}</Typography>
                )}
              </List>
            </Grid>

            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>{t("teams.edit.imageGen")}</Typography>
              <List>
                {team.image_generators?.length > 0 ? (
                  team.image_generators.map((gen) => (
                    <Fragment key={gen}>
                      <ListItem secondaryAction={
                        isTeamAdmin && (
                          <Tooltip title={t("teams.view.removeImageGen")}>
                            <IconButton edge="end" onClick={() => handleRemoveImageGenerator(gen)}>
                              <Delete />
                            </IconButton>
                          </Tooltip>
                        )
                      }>
                        <ListItemAvatar>
                          <Avatar>
                            <Image />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText primary={gen} />
                      </ListItem>
                      <Divider variant="inset" component="li" />
                    </Fragment>
                  ))
                ) : (
                  <Typography variant="body2" color="textSecondary">{t("teams.view.noImageGen")}</Typography>
                )}
              </List>
            </Grid>

            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>{t("teams.edit.audioGen")}</Typography>
              <List>
                {team.audio_generators?.length > 0 ? (
                  team.audio_generators.map((gen) => (
                    <Fragment key={gen}>
                      <ListItem secondaryAction={
                        isTeamAdmin && (
                          <Tooltip title={t("teams.view.removeAudioGen")}>
                            <IconButton edge="end" onClick={() => handleRemoveAudioGenerator(gen)}>
                              <Delete />
                            </IconButton>
                          </Tooltip>
                        )
                      }>
                        <ListItemAvatar>
                          <Avatar>
                            <Speaker />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText primary={gen} />
                      </ListItem>
                      <Divider variant="inset" component="li" />
                    </Fragment>
                  ))
                ) : (
                  <Typography variant="body2" color="textSecondary">{t("teams.view.noAudioGen")}</Typography>
                )}
              </List>
            </Grid>
          </Grid>
        </TabPanel>

        <TabPanel value={tabValue} index={3}>
            <MUIDataTable
              title={t("teams.view.transactions")}
              options={{
                print: false,
                selectableRows: "none",
                expandableRows: true,
                expandableRowsHeader: false,
                expandableRowsOnClick: true,
                download: false,
                filter: false,
                viewColumns: false,
                rowsExpanded: txRowsExpanded,
                rowsPerPage: txRows,
                rowsPerPageOptions: [50, 100, 500],
                elevation: 0,
                count: txCount,
                page: txPage,
                serverSide: true,
                textLabels: {
                  body: {
                    noMatch: t("teams.view.tx.noTransactions"),
                  },
                },
                onTableChange: (action, tableState) => {
                  switch (action) {
                    case 'changePage':
                      setTxPage(tableState.page);
                      break;
                    case 'changeRowsPerPage':
                      setTxRows(tableState.rowsPerPage);
                      setTxPage(0);
                      break;
                    default:
                      break;
                  }
                },
                isRowExpandable: () => true,
                renderExpandableRow: (rowData, rowMeta) => {
                  const colSpan = rowData.length + 1;
                  return (
                    <TableRow>
                      <TableCell sx={{ p: 2, backgroundColor: "#f0f0f0" }} colSpan={colSpan}>
                        <ReactJson src={txLog} enableClipboard={false} />
                      </TableCell>
                    </TableRow>
                  );
                },
                onRowExpansionChange: (_, allRowsExpanded) => {
                  setTxRowsExpanded(allRowsExpanded.slice(-1).map(item => item.index));
                  if (allRowsExpanded.length > 0) {
                    setTxLog(transactions[allRowsExpanded[0].dataIndex]);
                  }
                },
              }}
              data={transactions.map(tx => [
                tx.date,
                tx.project,
                tx.user,
                tx.llm,
                tx.input_tokens,
                tx.output_tokens,
                (tx.total_cost || 0),
              ])}
              columns={[
                {
                  name: t("teams.view.tx.date"),
                  options: {
                    customHeadRender: ({ index, ...column }) => (
                      <TableCell key={index} style={{ width: "180px" }}>{column.label}</TableCell>
                    ),
                    customBodyRender: (value) => new Date(value).toLocaleString(),
                  },
                },
                { name: t("teams.view.tx.project") },
                { name: t("teams.view.tx.user") },
                { name: t("teams.view.tx.llm") },
                { name: t("teams.view.tx.inTokens"), options: { customBodyRender: (value) => (value || 0).toLocaleString() } },
                { name: t("teams.view.tx.outTokens"), options: { customBodyRender: (value) => (value || 0).toLocaleString() } },
                {
                  name: t("teams.view.tx.cost"),
                  options: {
                    customBodyRender: (value) => (value || 0).toFixed(4),
                  },
                },
              ]}
            />
        </TabPanel>
      </StyledCard>
    </Container>
  );
}