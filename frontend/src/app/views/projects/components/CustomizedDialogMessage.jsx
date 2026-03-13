import CloseIcon from "@mui/icons-material/Close";
import { styled } from "@mui/material";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import MuiDialogActions from "@mui/material/DialogActions";
import MuiDialogContent from "@mui/material/DialogContent";
import MuiDialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import { useState, useEffect } from "react";
import ReactJson from '@microlink/react-json-view';

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

const CustomizedDialogMessage = ({ message, onclose }) => {
  const [open, setOpen] = useState(false);

  const handleClose = () => {
    setOpen(false);
    onclose();
  }

  useEffect(() => {
    if (message) {
      setOpen(true);
    }
  }, [message]);

  return (
    <div>
      <Dialog onClose={handleClose} aria-labelledby="customized-dialog-title" open={open}>
        <DialogTitle id="customized-dialog-title" onClose={handleClose}>
          Message Details
        </DialogTitle>

        <DialogContent dividers>
          <ReactJson src={message} enableClipboard={true} collapsed={1} name={false}/>
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

export default CustomizedDialogMessage;
