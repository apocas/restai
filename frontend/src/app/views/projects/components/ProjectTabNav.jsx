import { Fragment, useState } from "react";
import {
  Box,
  Card,
  Drawer,
  Button,
  IconButton,
  useTheme,
  useMediaQuery,
  styled,
} from "@mui/material";
import { ContentCopy } from "@mui/icons-material";
import { H5 } from "app/components/Typography";
import { FlexBox } from "app/components/FlexBox";

const StyledButton = styled(Button)(({ theme }) => ({
  borderRadius: 0,
  overflow: "hidden",
  position: "relative",
  whiteSpace: "nowrap",
  textOverflow: "ellipsis",
  padding: "0.6rem 1.5rem",
  justifyContent: "flex-start",
  color: theme.palette.text.primary,
}));

export default function ProjectTabNav({ tabs, active, setActive }) {
  const theme = useTheme();
  const [openDrawer, setOpenDrawer] = useState(false);
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
      backgroundColor: theme.palette.primary.main,
    },
  };

  function TabListContent() {
    return (
      <FlexBox flexDirection="column">
        {tabs.map(({ name, Icon }, index) => (
          <StyledButton
            key={index}
            startIcon={<Icon sx={{ color: "text.disabled" }} />}
            sx={active === name ? style : { "&:hover": style }}
            onClick={() => {
              setActive(name);
              setOpenDrawer(false);
            }}
          >
            {name}
          </StyledButton>
        ))}
      </FlexBox>
    );
  }

  if (downMd) {
    return (
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
    );
  }

  return (
    <Card sx={{ padding: "1rem 0" }}>
      <TabListContent />
    </Card>
  );
}
