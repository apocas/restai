import { Avatar, Box, styled } from "@mui/material";

const StyledAvatar = styled(Avatar)({
  height: 40,
  width: 40
});

export default function ChatAvatar({ src, status }) {
  return (
    <Box position="relative">
      <StyledAvatar src={src} />
    </Box>
  );
}
