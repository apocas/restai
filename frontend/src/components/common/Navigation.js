import React, { useContext } from 'react';
import { Container, Navbar, Button, Nav } from 'react-bootstrap';
import { NavLink } from "react-router-dom";
import { AuthContext } from './AuthProvider.js';
import restaiLogo from '../../assets/img/restai-logo.png';

function Navigation() {
  const { logout, getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth() || { username: null, admin: null };
  return (
    <Navbar expand="lg" className="bg-body-tertiary">
      <Container>
        <Navbar.Brand href="/admin">
          <img
            alt=""
            src={restaiLogo}
            width="30"
            height="30"
            className="d-inline-block align-top"
          />{' '}
          RestAI
        </Navbar.Brand>
        <Navbar.Toggle aria-controls="basic-navbar-nav" />
        <Navbar.Collapse id="basic-navbar-nav">
          <Nav className="me-auto">
            <Nav.Link as="li">
              <NavLink
                to="/"
              >
                Home
              </NavLink>
            </Nav.Link>
            {user.admin && (
              <Nav.Link as="li">
                <NavLink
                  to="/users"
                >
                  Users
                </NavLink>
              </Nav.Link>
            )}
            <Nav.Link as="li">
              <NavLink
                to="/hardware"
              >
                Hardware
              </NavLink>
            </Nav.Link>
          </Nav>
          {user.username && (
            <Nav>
              <Navbar.Text>
                Signed in as:  {' '}
                <NavLink
                  to={"/users/" + user.username}
                >
                  👤{user.username}{' | '}
                </NavLink>
                <NavLink
                  to={"/users/" + user.username + "/edit"}
                >
                  ⚙️Edit{' |'}
                </NavLink>
                <Button style={{ textDecoration: "none", color: "black", padding: "0px", verticalAlign: "0px" }} variant="link" onClick={logout}>
                  🚪Logout
                </Button>
              </Navbar.Text>
            </Nav>
          )}
        </Navbar.Collapse>
      </Container>
    </Navbar>
  );
}

export default Navigation;