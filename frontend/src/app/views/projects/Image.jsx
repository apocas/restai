import { styled, Box, Card } from "@mui/material";
import Breadcrumb from "app/components/Breadcrumb";
import { MatxSidenavContent } from "app/components/MatxSidenav";
import { MatxSidenavContainer } from "app/components/MatxSidenav";
import ImageChatContainer from "./components/ImageChatContainer";
import useAuth from "app/hooks/useAuth";
import { useState, useEffect } from "react";
import { toast } from 'react-toastify';

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));


export default function Image() {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();
  const [generators, setGenerators] = useState([]);

  const fetchGenerators = () => {
    return fetch(url + "/image", { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
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
        setGenerators(d.generators)
      }
      ).catch(err => {
        toast.error(err.toString());
      });
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
