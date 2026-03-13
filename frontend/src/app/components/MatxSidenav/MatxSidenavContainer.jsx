import { styled } from "@mui/material/styles";

const Container = styled("div")({
  height: "100%",
  display: "flex",
  position: "relative"
});

export default function MatxSidenavContainer({ children }) {
  return <Container>{children}</Container>;
}
