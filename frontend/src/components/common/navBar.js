import Container from 'react-bootstrap/Container';
import Navbar from 'react-bootstrap/Navbar';
import { NavLink } from "react-router-dom";

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
      </Container>
    </Navbar>
  );
}

export default CustomNavBar;