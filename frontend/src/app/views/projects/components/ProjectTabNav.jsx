import { Fragment, useState } from "react";
import {
  Box,
  Card,
  Drawer,
  Button,
  useMediaQuery,
  styled,
} from "@mui/material";
import { Menu as MenuIcon } from "@mui/icons-material";
import { useTranslation } from "react-i18next";
import { H5 } from "app/components/Typography";
import { FlexBox } from "app/components/FlexBox";

const StyledButton = styled(Button)(({ theme }) => ({
  borderRadius: 0,
  overflow: "hidden",
  position: "relative",
  whiteSpace: "nowrap",
  textOverflow: "ellipsis",
  padding: "0.7rem 1.25rem",
  justifyContent: "flex-start",
  color: theme.palette.text.secondary,
  fontSize: "0.85rem",
  fontWeight: 500,
  textTransform: "none",
  letterSpacing: 0,
  transition: "all 0.2s ease",
  borderBottom: `1px solid ${theme.palette.divider}`,
  "&:last-of-type": { borderBottom: "none" },
}));

export default function ProjectTabNav({ tabs, active, setActive }) {
  const { t } = useTranslation();
  const [openDrawer, setOpenDrawer] = useState(false);
  const downMd = useMediaQuery((theme) => theme.breakpoints.down("md"));

  const activeStyle = (theme) => ({
    color: theme.palette.primary.main,
    backgroundColor: theme.palette.action.selected,
    "&::before": {
      left: 0,
      width: 3,
      content: '""',
      height: "100%",
      position: "absolute",
      transition: "all 0.3s",
      backgroundColor: theme.palette.primary.main,
    },
  });

  const hoverStyle = (theme) => ({
    color: theme.palette.text.primary,
    backgroundColor: theme.palette.action.hover,
  });

  function TabListContent() {
    return (
      <FlexBox flexDirection="column">
        {tabs.map((tab, index) => {
          // `selectionId` is the stable identifier `setActive` receives
          // — the key prop when provided (i18n-safe), else the name.
          // Callers can switch to keys to keep `active` stable across
          // language changes. Existing call-sites that only pass `name`
          // still work unchanged.
          const { name, Icon, key } = tab;
          const selectionId = key || name;
          const isActive = active === selectionId;
          return (
            <StyledButton
              key={index}
              startIcon={<Icon sx={{ fontSize: 18 }} />}
              sx={(theme) =>
                isActive ? activeStyle(theme) : { "&:hover": hoverStyle(theme) }
              }
              onClick={() => {
                setActive(selectionId);
                setOpenDrawer(false);
              }}
            >
              {name}
            </StyledButton>
          );
        })}
      </FlexBox>
    );
  }

  // For the mobile "current tab" trigger: find the tab whose
  // selectionId matches `active` and show its translated name.
  const activeTab = tabs.find((tb) => (tb.key || tb.name) === active);
  const activeLabel = activeTab?.name;

  if (downMd) {
    // Mobile: the old treatment used a "Show More" label with a
    // ContentCopy icon that was both misleading and hard to find. Show
    // the currently-active tab as the trigger label with a Menu icon so
    // the user knows (a) where they are and (b) that it's tappable.
    return (
      <Fragment>
        <Button
          fullWidth
          startIcon={<MenuIcon />}
          variant="outlined"
          onClick={() => setOpenDrawer(true)}
          sx={{ justifyContent: "flex-start", mb: 2 }}
        >
          <H5 sx={{ m: 0, fontSize: 14 }}>{activeLabel || t("tabnav.menu")}</H5>
        </Button>

        <Drawer anchor="left" open={openDrawer} onClose={() => setOpenDrawer(false)}>
          <Box padding={1} sx={{ minWidth: 220 }}>
            <TabListContent />
          </Box>
        </Drawer>
      </Fragment>
    );
  }

  return (
    <Card
      elevation={0}
      sx={{
        py: 0.5,
        borderRadius: 3,
        border: "1px solid",
        borderColor: "divider",
        backgroundColor: "background.paper",
        overflow: "hidden",
      }}
    >
      <TabListContent />
    </Card>
  );
}
