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
import DeleteAccount from "./components/DeleteAccount";
import BasicInformation from "./components/BasicInformation";
import { toast } from 'react-toastify';
import InfoIcon from '@mui/icons-material/Info';
import KeyIcon from '@mui/icons-material/Key';
import HttpsIcon from '@mui/icons-material/Https';
import DeleteForeverIcon from '@mui/icons-material/DeleteForever';

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
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
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
    return fetch(url + "/users/" + username, { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
      .then((res) => res.json())
      .then((d) => {
        setUser(d)
        return d
      }).catch(err => {
        toast.error(err.toString());
      });
  }

  const fetchProjects = () => {
    return fetch(url + "/projects", { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            toast.error(data.detail);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
      .then((d) => {
        setProjects(d.projects)
      }
      ).catch(err => {
        toast.error(err.toString());
      });
  }

  const fetchInfo = () => {
    return fetch(url + "/info", { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            toast.error(data.detail);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
      .then((d) => setInfo(d)
      ).catch(err => {
        toast.error(err.toString());
      });
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
          {active === tabList[2].name && <Projects user={user} projects={projects} />}
          {active === tabList[3].name && <ApiKeys user={user} />}
          {active === tabList[4].name && <DeleteAccount user={user} />}
        </Grid>
      </Grid>
    </Box>
    </Container>
  );
}

const tabList = [
  { id: 1, name: "Basic Information", Icon: InfoIcon },
  { id: 2, name: "Password", Icon: HttpsIcon },
  { id: 3, name: "Projects", Icon: ContentCopy },
  { id: 12, name: "API Key", Icon: KeyIcon },
  { id: 13, name: "Delete account", Icon: DeleteForeverIcon }
];

