import { useState, useEffect, Fragment } from "react";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { useParams } from "react-router-dom";

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
  const { id } = useParams();
  const [projects, setProjects] = useState([]);
  const [user, setUser] = useState({});
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const auth = useAuth();
  const theme = useTheme();
  const [openDrawer, setOpenDrawer] = useState(false);
  const [active, setActive] = useState("Basic Information");
  const downMd = useMediaQuery((theme) => theme.breakpoints.down("md"));

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
            sx={active === name ? style : { "&:hover": style }}
            onClick={() => {
              setActive(name);
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
        <Breadcrumb routeSegments={[{ name: "Users", path: "/users"}, { name: id, path: "/user/" + id }]} />
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

                <H5>Show More</H5>
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
          {active === tabList[0].name && <BasicInformation user={user} />}
          {active === tabList[1].name && <Password user={user} />}
          {active === tabList[2].name && <TwoFactorAuth user={user} />}
          {active === tabList[3].name && <Projects user={user} projects={projects} />}
          {active === tabList[4].name && <ApiKeys user={user} />}
          {active === tabList[5].name && user.id && <UserActivity user={user} />}
          {active === tabList[6].name && <DeleteAccount user={user} />}
        </Grid>
      </Grid>
    </Box>
    </Container>
  );
}

const tabList = [
  { id: 1, name: "Basic Information", Icon: InfoIcon },
  { id: 2, name: "Password", Icon: HttpsIcon },
  { id: 15, name: "Two-Factor Auth", Icon: SecurityIcon },
  { id: 3, name: "Projects", Icon: ContentCopy },
  { id: 12, name: "API Keys", Icon: KeyIcon },
  { id: 14, name: "Activity", Icon: TimelineIcon },
  { id: 13, name: "Delete account", Icon: DeleteForeverIcon }
];

