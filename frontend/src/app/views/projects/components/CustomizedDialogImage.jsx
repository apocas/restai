import CloseIcon from "@mui/icons-material/Close";
import { styled, Box } from "@mui/material";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import MuiDialogActions from "@mui/material/DialogActions";
import MuiDialogContent from "@mui/material/DialogContent";
import MuiDialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
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

const CustomizedDialogImage = ({ image, onclose }) => {
  const [open, setOpen] = useState(false);

  const handleClose = () => {
    setOpen(false);
    onclose();
  }

  useEffect(() => {
    if (image) {
      setOpen(true);
    }
  }, [image]);

  return (
    <div>
      <Dialog onClose={handleClose} aria-labelledby="customized-dialog-title" open={open} fullWidth={false} maxWidth={"xl"}>
        <DialogTitle id="customized-dialog-title" onClose={handleClose}>
          Details
        </DialogTitle>

        <DialogContent dividers>
          <Box
            component="img"
            alt="Image preview"
            src={image}
            style={{ height: "100%" }}
          />
        </DialogContent>

        <DialogActions>
          <Button onClick={handleClose} color="primary">
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </div>
  );
};

export default CustomizedDialogImage;
