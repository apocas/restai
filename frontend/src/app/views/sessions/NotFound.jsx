import { Box, Button, styled } from "@mui/material";
import { useNavigate } from "react-router-dom";

const FlexBox = styled(Box)({
  display: "flex",
  alignItems: "center"
});

const JustifyBox = styled(FlexBox)({
  maxWidth: 600,
  flexDirection: "column",
  justifyContent: "center"
});

const IMG = styled("img")({
  width: "100%",
  marginBottom: "32px"
});

const NotFoundRoot = styled(FlexBox)({
  width: "100%",
  alignItems: "center",
  justifyContent: "center",
  height: "100vh !important"
});

export default function NotFound() {
  const navigate = useNavigate();

  return (
    <NotFoundRoot>
      <JustifyBox>
        <IMG src="/admin/assets/images/ai404.jpg" alt="" style={{borderRadius:"10%"}}/>

        <Button
          color="primary"
          variant="contained"
          sx={{ textTransform: "capitalize" }}
          onClick={() => navigate(-1)}>
          Go Back
        </Button>
      </JustifyBox>
    </NotFoundRoot>
  );
}
