import CloseIcon from "@mui/icons-material/Close";
import { styled, MenuItem } from "@mui/material";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import MuiDialogActions from "@mui/material/DialogActions";
import MuiDialogContent from "@mui/material/DialogContent";
import MuiDialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import { useState, useEffect } from "react";

const DialogTitleRoot = styled(MuiDialogTitle)(({ theme }) => ({
  margin: 0,
  padding: theme.spacing(2),
  "& .closeButton": {
    position: "absolute",
    right: theme.spacing(1),
    top: theme.spacing(1),
    color: theme.palette.grey[500],
  },
}));

const DialogTitle = (props) => {
  const { children, onClose } = props;
  return (
    <DialogTitleRoot disableTypography>
      <Typography variant="h6">{children}</Typography>
      {onClose ? (
        <IconButton aria-label="Close" className="closeButton" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      ) : null}
    </DialogTitleRoot>
  );
};

const DialogContent = styled(MuiDialogContent)(({ theme }) => ({
  "&.root": { padding: theme.spacing(2) },
}));

const DialogActions = styled(MuiDialogActions)(({ theme }) => ({
  "&.root": { margin: 0, padding: theme.spacing(1) },
}));

const CustomizedDialogEntrance = ({ project, projects, saveEntrances, onClose }) => {
  const [open, setOpen] = useState(false);
  const [entrance, setEntrance] = useState({});

  const handleClose = () => {
    setOpen(false);
    if (onClose)
      onClose();
  }

  const handleSave = () => {
    project.entrances.push(entrance);
    if (saveEntrances)
      saveEntrances();
    setOpen(false);
    setEntrance({});
    if (onClose)
      onClose();
  }

  useEffect(() => {
    if (project) {
      setOpen(true);
    }
  }, [project]);

  return (
    <div>
      <Dialog onClose={handleClose} aria-labelledby="customized-dialog-title" open={open}>
        <DialogTitle id="customized-dialog-title" onClose={handleClose}>
          Edit entrance
        </DialogTitle>

        <DialogContent dividers>
          <TextField
            autoFocus
            margin="dense"
            label="Name"
            fullWidth
            value={entrance.name}
            onChange={(e) => setEntrance({ ...entrance, name: e.target.value })}
          />
          <TextField
            select
            name="projectllm"
            margin="dense"
            label="Destination"
            fullWidth
            variant="outlined"
            onChange={(e) => setEntrance({ ...entrance, destination: e.target.value })}
            sx={{ minWidth: 188 }}
          >
            {projects.filter(item =>
              item.name
            ).map((item, ind) => (
              <MenuItem value={item.name} key={item.name}>
                {item.name}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            margin="dense"
            label="Description"
            fullWidth
            multiline
            rows={4}
            value={entrance.description}
            onChange={(e) => setEntrance({ ...entrance, description: e.target.value })}
          />
        </DialogContent>

        <DialogActions>
          <Button onClick={handleClose} color="primary">
            Close
          </Button>
          <Button onClick={handleSave} color="primary">
            Save
          </Button>
        </DialogActions>
      </Dialog>
    </div>
  );
};

export default CustomizedDialogEntrance;
