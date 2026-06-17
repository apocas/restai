import { useState, useEffect } from "react";
import {
  Box, Card, Typography, IconButton, Tooltip, CircularProgress, Chip, styled,
  Button, Switch, FormControlLabel, TextField, Divider,
} from "@mui/material";
import TableCell from "@mui/material/TableCell";
import {
  ArrowBack, ReceiptLong, AccountBalance, TrendingUp, TrendingDown,
  CreditCard, Autorenew, Delete,
} from "@mui/icons-material";
import MUIDataTable from "mui-datatables";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { formatCost } from "app/utils/utils";
import { FONT_MONO, sweep, shimmer, blink } from "app/components/page/pageStyles";
import TopUpBalanceDialog from "./TopUpBalanceDialog";
import PaymentCheckoutDialog from "./PaymentCheckoutDialog";

const ACCENT = "#0891b2";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

const HeroCard = styled(Card)(({ theme }) => ({
  position: "relative",
  padding: theme.spacing(3.5),
  marginBottom: theme.spacing(3),
  borderRadius: 20,
  overflow: "hidden",
  color: "#fff",
  background: `
    radial-gradient(at 18% 20%, rgba(14,165,233,0.92) 0px, transparent 55%),
    radial-gradient(at 82% 12%, rgba(6,182,212,0.85) 0px, transparent 55%),
    radial-gradient(at 75% 90%, rgba(56,189,248,0.65) 0px, transparent 55%),
    linear-gradient(135deg, #06182f 0%, #0c2748 100%)
  `,
  backgroundSize: "200% 200%, 200% 200%, 200% 200%, 100% 100%",
  animation: `${shimmer} 22s ease-in-out infinite`,
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 2,
    background: "linear-gradient(90deg, transparent, rgba(125,211,252,0.6), rgba(56,189,248,0.6), transparent)",
    animation: `${sweep} 6s ease-in-out infinite`,
    zIndex: 2,
  },
  "& > *": { position: "relative", zIndex: 1 },
}));

const sectionCardSx = {
  position: "relative",
  borderRadius: 2,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#fff",
  overflow: "hidden",
  boxShadow: "0 1px 2px rgba(15,23,42,0.04)",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 2,
    background: `linear-gradient(90deg, transparent, ${ACCENT}, transparent)`,
    transform: "translateX(-100%)",
    animation: `${sweep} 7s linear infinite`,
    opacity: 0.5,
    zIndex: 2,
  },
};

const heroIconBtnSx = {
  color: "rgba(255,255,255,0.85)",
  border: "1px solid rgba(255,255,255,0.16)",
  borderRadius: 1.5,
  background: "rgba(255,255,255,0.06)",
  backdropFilter: "blur(12px)",
  "&:hover": { color: "#fff", background: "rgba(255,255,255,0.14)" },
};

const KIND_STYLE = {
  topup:      { color: "#10b981", bg: "rgba(16,185,129,0.12)", border: "rgba(16,185,129,0.4)" },
  usage:      { color: "#475569", bg: "rgba(15,23,42,0.05)",  border: "rgba(15,23,42,0.15)" },
  adjustment: { color: "#f59e0b", bg: "rgba(245,158,11,0.12)", border: "rgba(245,158,11,0.4)" },
};

export default function TeamWallet() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [team, setTeam] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [balanceOpen, setBalanceOpen] = useState(false);
  const [checkoutOpen, setCheckoutOpen] = useState(false);

  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(0);
  const [perPage, setPerPage] = useState(50);

  const [payCfg, setPayCfg] = useState(null);
  const [arThreshold, setArThreshold] = useState("");
  const [arAmount, setArAmount] = useState("");
  const [arBusy, setArBusy] = useState(false);
  const [searchParams] = useSearchParams();

  const fetchTeam = () => {
    api.get(`/teams/${id}`, user.token, { silent: true })
      .then((d) => { setTeam(d); setLoading(false); })
      .catch((e) => { setError(e?.status === 403 ? "forbidden" : "error"); setLoading(false); });
  };

  const fetchLedger = () => {
    const start = page * perPage;
    api.get(`/teams/${id}/balance/transactions?start=${start}&end=${start + perPage}`, user.token, { silent: true })
      .then((d) => { setRows(d.transactions || []); setCount(d.total || 0); })
      .catch(() => {});
  };

  const fetchPayCfg = () => {
    api.get(`/teams/${id}/payment`, user.token, { silent: true })
      .then((d) => {
        setPayCfg(d);
        setArThreshold(d.auto_recharge_threshold != null ? String(d.auto_recharge_threshold) : "");
        setArAmount(d.auto_recharge_amount != null ? String(d.auto_recharge_amount) : "");
      })
      .catch(() => setPayCfg(null));
  };

  useEffect(() => { fetchTeam(); fetchPayCfg(); /* eslint-disable-next-line */ }, [id]);
  useEffect(() => { if (team) fetchLedger(); /* eslint-disable-next-line */ }, [team, page, perPage]);

  // Handle the provider return redirect (?payment=success|cancel|pending|error).
  useEffect(() => {
    const status = searchParams.get("payment");
    if (!status) return;
    if (status === "success") toast.success(t("teams.payment.success"), { position: "top-right" });
    else if (status === "pending") toast.info(t("teams.payment.pending"), { position: "top-right" });
    else if (status === "cancel") toast.info(t("teams.payment.canceled"), { position: "top-right" });
    else if (status === "error") toast.error(t("teams.payment.failed"), { position: "top-right" });
    navigate(`/team/${id}/wallet`, { replace: true });
    fetchTeam(); fetchLedger(); fetchPayCfg();
    /* eslint-disable-next-line */
  }, [searchParams]);

  useEffect(() => {
    if (team) document.title = `${process.env.REACT_APP_RESTAI_NAME || "RESTai"} - ${team.name} · ${t("teams.balance.ledger.title")}`;
  }, [team, t]);

  if (loading) {
    return <Container><Box sx={{ display: "flex", justifyContent: "center", py: 10 }}><CircularProgress /></Box></Container>;
  }
  if (error || !team) {
    return (
      <Container>
        <Card variant="outlined" sx={{ ...sectionCardSx, p: 4, textAlign: "center" }}>
          <Typography color="text.secondary">
            {error === "forbidden" ? t("teams.analytics.forbidden") : t("teams.analytics.loadError")}
          </Typography>
          <Box component="span" role="link" tabIndex={0}
            onClick={() => navigate(`/team/${id}`)}
            sx={{ display: "inline-block", mt: 2, color: ACCENT, cursor: "pointer", fontWeight: 600 }}>
            {t("teams.analytics.backToTeam")}
          </Box>
        </Card>
      </Container>
    );
  }

  const depleted = team.balance != null && team.balance <= 0;
  const providers = (payCfg && payCfg.payments_enabled) ? (payCfg.providers || []) : [];
  const canPay = providers.length > 0;
  const autoRechargeProviders = payCfg ? (payCfg.auto_recharge_providers || []) : [];
  const savedMethod = payCfg ? payCfg.saved_method : null;
  const arEnabled = payCfg ? payCfg.auto_recharge_enabled : false;

  const startSetup = () => {
    const prov = autoRechargeProviders[0] || "stripe";
    api.post(`/teams/${id}/payment/setup?provider=${prov}`, {}, user.token)
      .then((res) => { if (res && res.redirect_url) window.location.href = res.redirect_url; })
      .catch(() => {});
  };

  const saveAutoRecharge = (enabled) => {
    setArBusy(true);
    const body = {
      enabled,
      threshold: arThreshold !== "" ? parseFloat(arThreshold) : null,
      amount: arAmount !== "" ? parseFloat(arAmount) : null,
    };
    api.put(`/teams/${id}/payment/auto-recharge`, body, user.token)
      .then((d) => { setPayCfg(d); toast.success(t("teams.payment.autoRechargeSaved"), { position: "top-right" }); })
      .catch(() => {})
      .finally(() => setArBusy(false));
  };

  const removeMethod = () => {
    if (!window.confirm(t("teams.payment.removeMethodConfirm"))) return;
    api.delete(`/teams/${id}/payment/method`, user.token)
      .then((d) => { setPayCfg(d); toast.success(t("teams.payment.methodRemoved"), { position: "top-right" }); })
      .catch(() => {});
  };

  return (
    <Container>
      <HeroCard elevation={0}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 2, flexWrap: "wrap" }}>
          <Box sx={{ minWidth: 220 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, fontFamily: FONT_MONO, fontSize: "0.62rem", letterSpacing: 3, textTransform: "uppercase" }}>
              <Box component="span" role="link" tabIndex={0} onClick={() => navigate(`/team/${id}`)}
                sx={{ color: "rgba(255,255,255,0.75)", cursor: "pointer", "&:hover": { color: "#fff", textDecoration: "underline", textUnderlineOffset: 3 } }}>
                {team.name}
              </Box>
              <Box component="span" sx={{ color: "rgba(255,255,255,0.4)" }}>/</Box>
              <Box component="span" sx={{ color: "rgba(125,211,252,0.95)" }}>{t("teams.balance.ledger.eyebrow")}</Box>
            </Box>
            <Typography variant="h4" sx={{ fontWeight: 700, mt: 0.5, letterSpacing: "-0.5px", display: "flex", alignItems: "center", gap: 1 }}>
              <ReceiptLong sx={{ fontSize: 28, color: "rgba(125,211,252,0.95)" }} />
              {t("teams.balance.ledger.title")}
              <Box component="span" sx={{ width: 9, animation: `${blink} 1.1s steps(2,start) infinite`, color: "rgba(125,211,252,0.9)" }}>_</Box>
            </Typography>
            <Typography variant="body2" sx={{ mt: 0.5, color: "rgba(255,255,255,0.78)" }}>{t("teams.balance.ledger.subtitle")}</Typography>

            <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, mt: 2, px: 1.25, py: 0.75, borderRadius: 1.5,
              background: depleted ? "rgba(239,68,68,0.18)" : "rgba(16,185,129,0.16)",
              border: `1px solid ${depleted ? "rgba(239,68,68,0.5)" : "rgba(16,185,129,0.45)"}` }}>
              <AccountBalance sx={{ fontSize: 17, color: depleted ? "#fca5a5" : "#a7f3d0" }} />
              <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.92rem", fontWeight: 700, color: depleted ? "#fecaca" : "#d1fae5" }}>
                {depleted
                  ? t("teams.balance.depleted")
                  : t("teams.balance.available", { amount: formatCost(team.balance) })}
              </Typography>
            </Box>
          </Box>

          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            {canPay && (
              <Button
                variant="contained" size="small" startIcon={<CreditCard />}
                onClick={() => setCheckoutOpen(true)}
                sx={{ background: "rgba(255,255,255,0.16)", border: "1px solid rgba(255,255,255,0.28)",
                  backdropFilter: "blur(12px)", "&:hover": { background: "rgba(255,255,255,0.26)" } }}
              >
                {t("teams.payment.addFunds")}
              </Button>
            )}
            {user.is_admin && (
              <Tooltip title={t("teams.balance.topUp")}>
                <IconButton size="small" sx={heroIconBtnSx} onClick={() => setBalanceOpen(true)}><AccountBalance fontSize="small" /></IconButton>
              </Tooltip>
            )}
            <Tooltip title={t("teams.analytics.backToTeam")}>
              <IconButton size="small" sx={heroIconBtnSx} onClick={() => navigate(`/team/${id}`)}><ArrowBack fontSize="small" /></IconButton>
            </Tooltip>
          </Box>
        </Box>
      </HeroCard>

      <Card variant="outlined" sx={sectionCardSx}>
        <Box sx={{ px: 2.5, pt: 2, pb: 1.5, display: "flex", alignItems: "center", gap: 1.5, borderBottom: "1px solid", borderColor: "divider" }}>
          <ReceiptLong sx={{ fontSize: 16, color: ACCENT, flexShrink: 0 }} />
          <Typography sx={{ flex: 1, fontFamily: FONT_MONO, fontSize: "0.74rem", letterSpacing: "0.16em", textTransform: "uppercase", fontWeight: 800, color: "#0f172a" }}>
            {t("teams.balance.ledger.movements")}
          </Typography>
        </Box>
        <Box sx={{ p: 1.5 }}>
          <MUIDataTable
            title=""
            options={{
              print: false,
              selectableRows: "none",
              download: false,
              filter: false,
              search: false,
              viewColumns: false,
              elevation: 0,
              count,
              page,
              rowsPerPage: perPage,
              rowsPerPageOptions: [50, 100, 500],
              serverSide: true,
              textLabels: { body: { noMatch: t("teams.balance.ledger.noMovements") } },
              onTableChange: (action, tableState) => {
                if (action === "changePage") setPage(tableState.page);
                else if (action === "changeRowsPerPage") { setPerPage(tableState.rowsPerPage); setPage(0); }
              },
            }}
            data={rows.map((r) => [r.created_at, r.kind, r.amount, r.balance_after, r.actor_username, r.description])}
            columns={[
              { name: t("teams.balance.ledger.date"), options: {
                customHeadRender: ({ index, ...c }) => <TableCell key={index} style={{ width: 180 }}>{c.label}</TableCell>,
                customBodyRender: (v) => (
                  <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem" }}>
                    {v ? new Date(v).toLocaleString() : "—"}
                  </Box>
                ),
              } },
              { name: t("teams.balance.ledger.kind"), options: {
                customBodyRender: (v) => {
                  const s = KIND_STYLE[v] || KIND_STYLE.usage;
                  return (
                    <Chip
                      size="small"
                      label={t(`teams.balance.ledger.kind_${v}`, v)}
                      sx={{ fontFamily: FONT_MONO, fontSize: "0.64rem", fontWeight: 700, height: 20,
                        color: s.color, background: s.bg, border: `1px solid ${s.border}` }}
                    />
                  );
                },
              } },
              { name: t("teams.balance.ledger.amount"), options: {
                customBodyRender: (v) => {
                  const inMove = Number(v) >= 0;
                  const color = inMove ? "#10b981" : "#ef4444";
                  const Icon = inMove ? TrendingUp : TrendingDown;
                  return (
                    <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.4, fontFamily: FONT_MONO, fontWeight: 700, color }}>
                      <Icon sx={{ fontSize: 14 }} />
                      {inMove ? "+" : "−"}{formatCost(v)}
                    </Box>
                  );
                },
              } },
              { name: t("teams.balance.ledger.balanceAfter"), options: {
                customBodyRender: (v) => <Box component="span" sx={{ fontFamily: FONT_MONO, fontWeight: 600 }}>{formatCost(v)}</Box>,
              } },
              { name: t("teams.balance.ledger.actor"), options: {
                customBodyRender: (v) => v
                  ? <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem" }}>{v}</Box>
                  : <Box component="span" sx={{ color: "text.disabled" }}>—</Box>,
              } },
              { name: t("teams.balance.ledger.description"), options: {
                customBodyRender: (v) => v
                  ? <Typography component="span" variant="caption" color="text.secondary">{v}</Typography>
                  : <Box component="span" sx={{ color: "text.disabled" }}>—</Box>,
              } },
            ]}
          />
        </Box>
      </Card>

      {autoRechargeProviders.length > 0 && (
        <Card variant="outlined" sx={{ ...sectionCardSx, mt: 2.5 }}>
          <Box sx={{ px: 2.5, pt: 2, pb: 1.5, display: "flex", alignItems: "center", gap: 1.5, borderBottom: "1px solid", borderColor: "divider" }}>
            <Autorenew sx={{ fontSize: 16, color: ACCENT, flexShrink: 0 }} />
            <Typography sx={{ flex: 1, fontFamily: FONT_MONO, fontSize: "0.74rem", letterSpacing: "0.16em", textTransform: "uppercase", fontWeight: 800, color: "#0f172a" }}>
              {t("teams.payment.autoRecharge")}
            </Typography>
          </Box>
          <Box sx={{ p: 2.5 }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {t("teams.payment.autoRechargeHelp")}
            </Typography>
            {!savedMethod ? (
              <Button variant="outlined" startIcon={<CreditCard />} onClick={startSetup}>
                {t("teams.payment.saveACard")}
              </Button>
            ) : (
              <Box>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                  <CreditCard sx={{ fontSize: 18, color: "text.secondary" }} />
                  <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.85rem" }}>
                    {(savedMethod.brand || "card")} •••• {savedMethod.last4 || "----"}
                  </Typography>
                  <Tooltip title={t("teams.payment.removeMethod")}>
                    <IconButton size="small" onClick={removeMethod} sx={{ color: "text.disabled", "&:hover": { color: "#ef4444" } }}>
                      <Delete fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
                <FormControlLabel
                  control={<Switch checked={!!arEnabled} onChange={(e) => saveAutoRecharge(e.target.checked)} disabled={arBusy} />}
                  label={t("teams.payment.autoRechargeEnabled")}
                />
                <Divider sx={{ my: 1.5 }} />
                <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", alignItems: "flex-end" }}>
                  <TextField
                    type="number" size="small" label={t("teams.payment.threshold")}
                    value={arThreshold} onChange={(e) => setArThreshold(e.target.value)}
                    helperText={t("teams.payment.thresholdHelp")} sx={{ width: 200 }}
                  />
                  <TextField
                    type="number" size="small" label={t("teams.payment.rechargeAmount")}
                    value={arAmount} onChange={(e) => setArAmount(e.target.value)}
                    helperText={t("teams.payment.rechargeAmountHelp")} sx={{ width: 200 }}
                  />
                  <Button variant="contained" onClick={() => saveAutoRecharge(arEnabled)} disabled={arBusy}>
                    {t("common.save")}
                  </Button>
                </Box>
              </Box>
            )}
          </Box>
        </Card>
      )}

      {canPay && (
        <PaymentCheckoutDialog
          open={checkoutOpen}
          onClose={() => setCheckoutOpen(false)}
          teamId={id}
          providers={providers}
          autoRechargeProviders={autoRechargeProviders}
        />
      )}

      {user.is_admin && (
        <TopUpBalanceDialog
          open={balanceOpen}
          onClose={() => setBalanceOpen(false)}
          teamId={id}
          current={team.balance}
          onSaved={(updated) => { setBalanceOpen(false); if (updated) setTeam(updated); else fetchTeam(); fetchLedger(); }}
        />
      )}
    </Container>
  );
}
