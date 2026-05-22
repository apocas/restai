import { Box, styled } from "@mui/material";
import clsx from "clsx";

const StyledBox = styled(Box)(({ ellipsis }) => ({
  textTransform: "none",
  ...(ellipsis && { whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" })
}));

export const H1 = ({ children, className, ellipsis, ...props }) => {
  return (
    <StyledBox
      mb={0}
      mt={0}
      component="h1"
      fontSize="28px"
      fontWeight="500"
      lineHeight="1.5"
      ellipsis={ellipsis}
      className={clsx({ [className || ""]: true })}
      {...props}>
      {children}
    </StyledBox>
  );
};

export const H2 = ({ children, className, ellipsis, ...props }) => {
  return (
    <StyledBox
      mb={0}
      mt={0}
      component="h2"
      fontSize="24px"
      fontWeight="500"
      lineHeight="1.5"
      ellipsis={ellipsis}
      className={clsx({ [className || ""]: true })}
      {...props}>
      {children}
    </StyledBox>
  );
};

export const H3 = ({ children, className, ellipsis, ...props }) => {
  return (
    <StyledBox
      mb={0}
      mt={0}
      component="h3"
      fontSize="18px"
      fontWeight="500"
      lineHeight="1.5"
      ellipsis={ellipsis}
      className={clsx({ [className || ""]: true })}
      {...props}>
      {children}
    </StyledBox>
  );
};

export const H4 = ({ children, className, ellipsis, ...props }) => {
  return (
    <StyledBox
      mb={0}
      mt={0}
      component="h4"
      fontSize="16px"
      fontWeight="500"
      lineHeight="1.5"
      ellipsis={ellipsis}
      className={clsx({ [className || ""]: true })}
      {...props}>
      {children}
    </StyledBox>
  );
};

export const H5 = ({ children, className, ellipsis, ...props }) => {
  return (
    <StyledBox
      mb={0}
      mt={0}
      component="h5"
      fontSize="14px"
      fontWeight="500"
      lineHeight="1.5"
      ellipsis={ellipsis}
      className={clsx({ [className || ""]: true })}
      {...props}>
      {children}
    </StyledBox>
  );
};

export const H6 = ({ children, className, ellipsis, ...props }) => {
  return (
    <StyledBox
      mb={0}
      mt={0}
      component="h6"
      fontSize="13px"
      fontWeight="500"
      lineHeight="1.5"
      ellipsis={ellipsis}
      className={clsx({ [className || ""]: true })}
      {...props}>
      {children}
    </StyledBox>
  );
};

export const Paragraph = ({ children, className, ellipsis, ...props }) => {
  return (
    <StyledBox
      mb={0}
      mt={0}
      component="p"
      fontSize="14px"
      ellipsis={ellipsis}
      className={clsx({ [className || ""]: true })}
      {...props}>
      {children}
    </StyledBox>
  );
};

export const Small = ({ children, className, ellipsis, ...props }) => {
  return (
    <StyledBox
      fontSize="12px"
      fontWeight="500"
      lineHeight="1.5"
      component="small"
      ellipsis={ellipsis}
      className={clsx({ [className || ""]: true })}
      {...props}>
      {children}
    </StyledBox>
  );
};

export const Span = ({ children, className, ellipsis, ...props }) => {
  return (
    <StyledBox
      component="span"
      lineHeight="1.5"
      ellipsis={ellipsis}
      className={clsx({ [className || ""]: true })}
      {...props}>
      {children}
    </StyledBox>
  );
};

export const Tiny = ({ children, className, ellipsis, ...props }) => {
  return (
    <StyledBox
      fontSize="10px"
      lineHeight="1.5"
      component="small"
      ellipsis={ellipsis}
      className={clsx({ [className || ""]: true })}
      {...props}>
      {children}
    </StyledBox>
  );
};
