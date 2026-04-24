import React, { useState } from 'react';
import { Card, Box, Divider, Stack, Checkbox, Button } from '@mui/material';
import { H5, H6, Paragraph } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

export default function DeleteAccount({user}) {
  const { t } = useTranslation();
  const [isChecked, setIsChecked] = useState(false);
  const auth = useAuth();
  const navigate = useNavigate();

  const handleDeleteClick = () => {
    if (isChecked) {
      api.delete("/users/" + user.username, auth.user.token)
        .then(() => {
          navigate("/users");
        })
        .catch(() => {});
    }
  };

  return (
    <Card sx={{ pb: 3 }}>
      <Box padding={3}>
        <H5 mb={1}>{t("users.deleteAccount.title")}</H5>
        <Paragraph lineHeight={1.7} maxWidth={600}>
          {t("users.deleteAccount.description")}
        </Paragraph>
      </Box>
      

      <Divider />

      <Stack direction="row" alignItems="center" spacing={1} p={2}>
        <Checkbox checked={isChecked} onChange={(e) => setIsChecked(e.target.checked)} />
        <H6 fontSize={12}>{t("users.deleteAccount.confirm")}</H6>
      </Stack>

      <Stack px={3} direction="row" spacing={2}>
        <Button variant="contained" color="error" onClick={handleDeleteClick} disabled={!isChecked}>
          {t("users.deleteAccount.delete")}
        </Button>
      </Stack>
    </Card>
  );
}
