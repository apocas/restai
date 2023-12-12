import React, { useContext, useEffect, useState } from 'react';
import { Container, Navbar, Button, Nav } from 'react-bootstrap';
import { NavLink } from "react-router-dom";
import { AuthContext } from './AuthProvider.js';
import restaiLogo from '../../assets/img/restai-logo.png';


function Navigation() {
  const { logout, getBasicAuth, checkAuth } = useContext(AuthContext);
  const [hardware, setHardware] = useState({ "gpu_ram_usage": 0, "models_vram": [] });
  const user = getBasicAuth() || { username: null, admin: null };
  const [error, setError] = useState([]);

  const url = process.env.REACT_APP_RESTAI_API_URL || "";

  const fetchHardware = () => {
    return fetch(url + "/hardware", { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => setHardware(d)
      ).catch(err => {
        setError([...error, { "functionName": "fetchHardware", "error": err.toString() }]);
      });
  }

  useEffect(() => {
    fetchHardware();

    const intervalCall = setInterval(() => {
      if(checkAuth()) {
        fetchHardware();
      }
    }, 15000);
  }, []);

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
                Projects
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
            <Nav.Link as="li">|</Nav.Link>
            <Nav.Link as="li">
              <NavLink
                to="/hardware"
              >
                Hardware
              </NavLink>
            </Nav.Link>
            <Nav.Link as="li">
              <NavLink
                to="/Models"
              >
                Models
              </NavLink>
            </Nav.Link>
            <Nav.Link as="li">
              <a href="/docs">API</a>
            </Nav.Link>
          </Nav>
          {user.username && (
            <Nav>
              <Navbar.Text style={{  marginRight: '5px' }}>
                <b>Models@VRAM:</b> {hardware && hardware.models_vram && hardware.models_vram.join(', ')}{' -'}
              </Navbar.Text>
              <Navbar.Text style={{ color: hardware && hardware.gpu_ram_usage > 80 ? 'red' : 'inherit', marginRight: '5px' }}>
              <b>VRAM:</b> {hardware && hardware.gpu_ram_usage}{'% -'}
              </Navbar.Text>
              <Navbar.Text>
              <b>Signed in as:</b>  {' '}
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