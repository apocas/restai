import { styled, Box, Card } from "@mui/material";
import Breadcrumb from "app/components/Breadcrumb";
import { MatxSidenavContent } from "app/components/MatxSidenav";
import { MatxSidenavContainer } from "app/components/MatxSidenav";
import AudioChatContainer from "./components/AudioChatContainer";
import useAuth from "app/hooks/useAuth";
import { useState, useEffect } from "react";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));


export default function Audio() {
  const auth = useAuth();
  const [generators, setGenerators] = useState([]);

  const fetchGenerators = () => {
    return api.get("/audio", auth.user.token)
      .then((d) => {
        setGenerators(d.generators)
      })
      .catch(() => {});
  }

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Audio Generation';
    fetchGenerators();
  }, []);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Audio", path: "/audio"}]} />
      </Box>

      <Card elevation={6}>
        <MatxSidenavContainer>
          <MatxSidenavContent>
            <AudioChatContainer generators={generators}/>
          </MatxSidenavContent>
        </MatxSidenavContainer>
      </Card>
    </Container>

  );
}
