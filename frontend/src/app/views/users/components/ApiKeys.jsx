import {
  Box,
  Card,
  Button,
  Divider,
  Stack
} from "@mui/material";

import { FlexBetween } from "app/components/FlexBox";
import { H5 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import { toast } from 'react-toastify';

export default function ApiKeys({user}) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();

  const apikeyClick = () => {
    if (window.confirm("This will invalidate your current API Key and generate a new one. Are you sure?")) {
      fetch(url + "/users/" + user.username + "/apikey", {
        method: 'POST',
        headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
      })
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
        .then((response) => {
          if (response) {
            alert(response.api_key);
          } else {
            alert("No key...");
          }
        }).catch(err => {
          toast.error(err.toString());
        });
    }
  }

  return (
    <Card>
      <FlexBetween px={3} py={2}>
        <H5>API Key</H5>
      </FlexBetween>

      <Divider />

      <Box padding={3}>
        <Stack direction="row" spacing={3} mt={0}>
          <Button type="submit" variant="contained" onClick={() => { apikeyClick() }}>
            Generate new key
          </Button>
        </Stack>
      </Box>

    </Card>
  );
}
