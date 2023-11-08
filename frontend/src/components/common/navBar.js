import Container from 'react-bootstrap/Container';
import Navbar from 'react-bootstrap/Navbar';
import { NavLink } from "react-router-dom";
import Nav from 'react-bootstrap/Nav';

function CustomNavBar() {
  return (
    <Navbar expand="lg" className="bg-body-tertiary">
      <Container>
        <Navbar.Brand>
          <NavLink
            to="/"
          >
            RestAI
          </NavLink>
        </Navbar.Brand>
        <Navbar.Toggle aria-controls="basic-navbar-nav" />
        <Navbar.Collapse id="basic-navbar-nav">
          <Nav className="me-auto">
            <Nav.Link href="#home">
              <NavLink
                to="/"
              >
                Home
              </NavLink>
            </Nav.Link>
          </Nav>
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
}

export default CustomNavBar;