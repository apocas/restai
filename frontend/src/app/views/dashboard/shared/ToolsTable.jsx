import { useState } from "react";
import {
  Box,
  Card,
  Table,
  Avatar,
  styled,
  TableRow,
  useTheme,
  TableBody,
  TableCell,
  TableHead,
  Button,
  TablePagination
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import Highlight from 'react-highlight';


const CardHeader = styled(Box)(() => ({
  display: "flex",
  paddingLeft: "24px",
  paddingRight: "24px",
  marginBottom: "12px",
  alignItems: "center",
  justifyContent: "space-between"
}));

const Title = styled("span")(() => ({
  fontSize: "1rem",
  fontWeight: "500",
  textTransform: "capitalize"
}));

const ProductTable = styled(Table)(() => ({
  minWidth: 400,
  whiteSpace: "pre",
  "& small": {
    width: 50,
    height: 15,
    borderRadius: 500,
    boxShadow: "0 0 2px 0 rgba(0, 0, 0, 0.12), 0 2px 2px 0 rgba(0, 0, 0, 0.24)"
  },
  "& td": { borderBottom: "none" },
  "& td:first-of-type": { paddingLeft: "16px !important" }
}));


export default function ProjectsTable({ tools = [], title = "Tools" }) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  const handleChangePage = (_, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(+event.target.value);
    setPage(0);
  };

  return (
    <Card elevation={3} sx={{ pt: "20px", mb: 3 }}>
      <CardHeader>
        <Title>{title}</Title>
      </CardHeader>

      <Box overflow="auto">
        <ProductTable>
          <TableHead>
            <TableRow>

            </TableRow>
          </TableHead>

          <TableBody>
            {tools.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage).map((tool, index) => (
              <TableRow key={index} hover>
                <TableCell align="left" >
                <h4>{tool.name}</h4>
                  <Highlight className='python'>
                    {tool.description}
                  </Highlight>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </ProductTable>

        {tools && tools.length > 25 && (
          <TablePagination
            sx={{ px: 2 }}
            page={page}
            component="div"
            rowsPerPage={rowsPerPage}
            count={tools.length}
            onPageChange={handleChangePage}
            rowsPerPageOptions={[25, 50, 100]}
            onRowsPerPageChange={handleChangeRowsPerPage}
          />
        )}
      </Box >
    </Card >
  );
}
