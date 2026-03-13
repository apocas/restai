import Chat from "@mui/icons-material/Chat";
import { styled } from "@mui/material/styles";
import { FlexAlignCenter } from "app/components/FlexBox";

const Container = styled(FlexAlignCenter)(({ theme }) => ({
  width: 220,
  height: 220,
  overflow: "hidden",
  borderRadius: "300px",
  background: theme.palette.background.default,
  "& span": { fontSize: "4rem" }
}));

export default function EmptyMessage() {
  return (
    <Container>
      <Chat color="primary" />
    </Container>
  );
}
