import React, { useContext } from 'react';
import { Container, Navbar, Button, Nav } from 'react-bootstrap';
import { NavLink } from "react-router-dom";
import { AuthContext } from './AuthProvider.js';

function Navigation() {
  const { logout, getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth() || { username: null, admin: null };
  return (
    <Navbar expand="lg" className="bg-body-tertiary">
      <Container>
        <Navbar.Brand href="/admin">
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
                Signed in as:                         <NavLink
                  to={"/users/" + user.username}
                >
                  {user.username}{' '}
                </NavLink>
                <Button variant="link" onClick={logout}>
                  Logout
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