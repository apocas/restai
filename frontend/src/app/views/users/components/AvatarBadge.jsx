import { Badge, styled } from "@mui/material";

const StyledBadge = styled(Badge)(({ theme, width, height }) => ({
  "& .MuiBadge-badge": {
    width: width,
    height: height,
    borderRadius: "50%",
    backgroundColor: theme.palette.primary.main,
    boxShadow: `0 0 0 2px ${theme.palette.background.paper}`
  },
  "& .MuiBadge-colorSuccess.MuiBadge-badge": {
    backgroundColor: theme.palette.success.main,
    boxShadow: `0 0 0 1px ${theme.palette.background.paper}`
  }
}));

export default function AvatarBadge({ children, width, height, ...props }) {
  return (
    <StyledBadge
      width={width || 10}
      height={height || 10}
      overlap="circular"
      anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      {...props}>
      {children}
    </StyledBadge>
  );
}
