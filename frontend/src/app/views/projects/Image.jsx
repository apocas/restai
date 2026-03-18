import { styled, Box, Card } from "@mui/material";
import Breadcrumb from "app/components/Breadcrumb";
import { MatxSidenavContent } from "app/components/MatxSidenav";
import { MatxSidenavContainer } from "app/components/MatxSidenav";
import ImageChatContainer from "./components/ImageChatContainer";
import useAuth from "app/hooks/useAuth";
import { useState, useEffect } from "react";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));


export default function Image() {
  const auth = useAuth();
  const [generators, setGenerators] = useState([]);

  const fetchGenerators = () => {
    return api.get("/image", auth.user.token)
      .then((d) => {
        setGenerators(d.generators)
      })
      .catch(() => {});
  }

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Image Generation';
    fetchGenerators();
  }, []);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Image", path: "/image"}]} />
      </Box>

      <Card elevation={6}>
        <MatxSidenavContainer>
          <MatxSidenavContent>
            <ImageChatContainer generators={generators}/>
          </MatxSidenavContent>
        </MatxSidenavContainer>
      </Card>
    </Container>

  );
}
