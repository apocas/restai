import { Card, Grid, IconButton } from "@mui/material";
import { People, AccountTree } from "@mui/icons-material";
import { H3, Paragraph } from "app/components/Typography";

export default function Overview({ projects = [], title = "Overview" }) {
  var users = [];
  projects.forEach((project) => {
    project.users.forEach((user) => {
      if (!users.includes(user.username)) {
        users.push(user.username);
      }
    });
  });

  return (
    <div>
      <Grid container spacing={3}>
        <Grid item md={3} sm={6} xs={12}>
          <Card elevation={3} sx={{ mb: 3, p: "20px", display: "flex", gap: 2, alignItems: "start" }}>
            <IconButton size="small" sx={{ padding: 1, backgroundColor: "divider" }}>
              <AccountTree color="primary" />
            </IconButton>

            <div>
              <H3 mb={0.5} lineHeight={1} fontSize={28}>
                {projects.length}
              </H3>

              <Paragraph color="text.secondary">{"Active Projects"}</Paragraph>
            </div>
          </Card>
        </Grid>

        <Grid item md={3} sm={6} xs={12}>
          <Card elevation={3} sx={{ mb: 3, p: "20px", display: "flex", gap: 2, alignItems: "start" }}>
            <IconButton size="small" sx={{ padding: 1, backgroundColor: "divider" }}>
              <People color="primary" />
            </IconButton>

            <div>
              <H3 mb={0.5} lineHeight={1} fontSize={28}>
                {users.length}
              </H3>

              <Paragraph color="text.secondary">{"Shared with"}</Paragraph>
            </div>
          </Card>
        </Grid>
      </Grid>
    </div>
  );
}
