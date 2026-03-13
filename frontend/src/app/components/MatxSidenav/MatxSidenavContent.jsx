import { styled } from "@mui/material/styles";

const Content = styled("div")({
  flexGrow: 1,
  height: "100%",
  position: "relative"
});

export default function MatxSidenavContent({ children }) {
  return <Content>{children}</Content>;
}
