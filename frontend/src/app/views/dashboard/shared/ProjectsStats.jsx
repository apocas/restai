import { Card, Grid, IconButton } from "@mui/material";
import { People, AccountTree, Token, AttachMoney, Groups } from "@mui/icons-material";
import { H3, Paragraph } from "app/components/Typography";

const CURRENCY_SYMBOLS = { USD: "$", EUR: "\u20AC" };

export default function Overview({ projects = [], summary = null, currency = "USD" }) {
  const currencySymbol = CURRENCY_SYMBOLS[currency] || "$";
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
                {summary ? summary.total_projects : projects.length}
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
                {summary ? summary.total_users : users.length}
              </H3>

              <Paragraph color="text.secondary">{summary ? "Total Users" : "Shared with"}</Paragraph>
            </div>
          </Card>
        </Grid>

        {summary && (
          <>
            <Grid item md={3} sm={6} xs={12}>
              <Card elevation={3} sx={{ mb: 3, p: "20px", display: "flex", gap: 2, alignItems: "start" }}>
                <IconButton size="small" sx={{ padding: 1, backgroundColor: "divider" }}>
                  <Token color="primary" />
                </IconButton>
                <div>
                  <H3 mb={0.5} lineHeight={1} fontSize={28}>
                    {(summary.total_tokens || 0).toLocaleString()}
                  </H3>
                  <Paragraph color="text.secondary">Total Tokens</Paragraph>
                </div>
              </Card>
            </Grid>

            <Grid item md={3} sm={6} xs={12}>
              <Card elevation={3} sx={{ mb: 3, p: "20px", display: "flex", gap: 2, alignItems: "start" }}>
                <IconButton size="small" sx={{ padding: 1, backgroundColor: "divider" }}>
                  <AttachMoney color="primary" />
                </IconButton>
                <div>
                  <H3 mb={0.5} lineHeight={1} fontSize={28}>
                    {currencySymbol}{(summary.total_cost || 0).toFixed(2)}
                  </H3>
                  <Paragraph color="text.secondary">Total Cost</Paragraph>
                </div>
              </Card>
            </Grid>
          </>
        )}
      </Grid>
    </div>
  );
}
