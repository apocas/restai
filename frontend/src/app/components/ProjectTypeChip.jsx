import { Chip } from "@mui/material";
import { PROJECT_TYPE_COLORS } from "app/utils/constant";

const DEFAULT_STYLE = { bg: "rgba(239,68,68,0.12)", color: "#ef4444" };

export default function ProjectTypeChip({ type, ...props }) {
  const style = PROJECT_TYPE_COLORS[type] || DEFAULT_STYLE;
  return (
    <Chip
      label={type}
      size="small"
      sx={{
        backgroundColor: style.bg,
        color: style.color,
        fontWeight: 600,
        fontSize: "0.72rem",
        textTransform: "uppercase",
        height: 22,
      }}
      {...props}
    />
  );
}
