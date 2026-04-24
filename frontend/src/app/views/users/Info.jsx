import { useState, useEffect, Fragment } from "react";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import {
  Box,
  Card,
  Grid,
  styled,
  Drawer,
  Button,
  useTheme,
  IconButton,
  useMediaQuery
} from "@mui/material";

import { H5 } from "app/components/Typography";
import { FlexBox } from "app/components/FlexBox";
import { ContentCopy } from "@mui/icons-material";

import ApiKeys from "./components/ApiKeys";
import Password from "./components/Password";
import Projects from "./components/Projects";
import Teams from "./components/Teams";
import UserActivity from "./components/UserActivity";
import DeleteAccount from "./components/DeleteAccount";
import TwoFactorAuth from "./components/TwoFactorAuth";
import BasicInformation from "./components/BasicInformation";
import api from "app/utils/api";
import InfoIcon from '@mui/icons-material/Info';
import KeyIcon from '@mui/icons-material/Key';
import HttpsIcon from '@mui/icons-material/Https';
import DeleteForeverIcon from '@mui/icons-material/DeleteForever';
import TimelineIcon from '@mui/icons-material/Timeline';
import SecurityIcon from '@mui/icons-material/Security';
import GroupsIcon from '@mui/icons-material/Groups';

const StyledButton = styled(Button)(({ theme }) => ({
  borderRadius: 0,
  overflow: "hidden",
  position: "relative",
  whiteSpace: "nowrap",
  textOverflow: "ellipsis",
  padding: "0.6rem 1.5rem",
  justifyContent: "flex-start",
  color: theme.palette.text.primary
}));


const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));


export default function UserInfo() {
  const { t } = useTranslation();
  const { id } = useParams();
  const [projects, setProjects] = useState([]);
  const [user, setUser] = useState({});
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const auth = useAuth();
  const theme = useTheme();
  const [openDrawer, setOpenDrawer] = useState(false);
  const [active, setActive] = useState("basic");
  const downMd = useMediaQuery((theme) => theme.breakpoints.down("md"));

  const tabList = [
    { id: "basic", name: t("users.tabs.basic"), Icon: InfoIcon },
    { id: "password", name: t("users.tabs.password"), Icon: HttpsIcon },
    { id: "twoFactor", name: t("users.tabs.twoFactor"), Icon: SecurityIcon },
    { id: "projects", name: t("users.tabs.projects"), Icon: ContentCopy },
    { id: "teams", name: t("users.tabs.teams"), Icon: GroupsIcon },
    { id: "apiKeys", name: t("users.tabs.apiKeys"), Icon: KeyIcon },
    { id: "activity", name: t("users.tabs.activity"), Icon: TimelineIcon },
    { id: "delete", name: t("users.tabs.delete"), Icon: DeleteForeverIcon }
  ];

  const style = {
    color: theme.palette.primary.main,
    backgroundColor: theme.palette.grey[100],
    "&::before": {
      left: 0,
      width: 4,
      content: '""',
      height: "100%",
      position: "absolute",
      transition: "all 0.3s",
      backgroundColor: theme.palette.primary.main
    }
  };

  function TabListContent() {
    return (
      <FlexBox flexDirection="column">
        {tabList.map(({ id, name, Icon }) => (
          <StyledButton
            key={id}
            startIcon={<Icon sx={{ color: "text.disabled" }} />}
            sx={active === id ? style : { "&:hover": style }}
            onClick={() => {
              setActive(id);
              setOpenDrawer(false);
            }}>
            {name}
          </StyledButton>
        ))}
      </FlexBox>
    );
  }

  const fetchUser = (username) => {
    return api.get("/users/" + username, auth.user.token)
      .then((d) => {
        setUser(d)
        return d
      })
      .catch(() => {});
  }

  const fetchProjects = () => {
    return api.get("/projects", auth.user.token)
      .then((d) => {
        setProjects(d.projects)
      })
      .catch(() => {});
  }

  const fetchInfo = () => {
    return api.get("/info", auth.user.token)
      .then((d) => setInfo(d))
      .catch(() => {});
  }

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Project - ' + id;
    fetchUser(id);
  }, [id]);

  useEffect(() => {
    fetchProjects();
    fetchInfo();
  }, []);


  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("nav.users"), path: "/users"}, { name: id, path: "/user/" + id }]} />
      </Box>

      <Box p={4} pt={0}>
      <Grid container spacing={3}>
        <Grid item md={3} xs={12}>
          {downMd ? (
            <Fragment>
              <FlexBox alignItems="center" gap={1}>
                <IconButton sx={{ padding: 0 }} onClick={() => setOpenDrawer(true)}>
                  <ContentCopy sx={{ color: "primary.main" }} />
                </IconButton>

                <H5>{t("users.showMore")}</H5>
              </FlexBox>

              <Drawer open={openDrawer} onClose={() => setOpenDrawer(false)}>
                <Box padding={1}>
                  <TabListContent />
                </Box>
              </Drawer>
            </Fragment>
          ) : (
            <Card sx={{ padding: "1rem 0" }}>
              <TabListContent />
            </Card>
          )}
        </Grid>

        <Grid item md={9} xs={12}>
          {active === "basic" && <BasicInformation user={user} />}
          {active === "password" && <Password user={user} />}
          {active === "twoFactor" && <TwoFactorAuth user={user} />}
          {active === "projects" && <Projects user={user} projects={projects} />}
          {active === "teams" && <Teams user={user} />}
          {active === "apiKeys" && <ApiKeys user={user} />}
          {active === "activity" && user.id && <UserActivity user={user} />}
          {active === "delete" && <DeleteAccount user={user} />}
        </Grid>
      </Grid>
    </Box>
    </Container>
  );
}

