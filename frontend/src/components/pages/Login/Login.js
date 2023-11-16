import { Form, Button, Alert } from "react-bootstrap";
import React, { useState, useContext } from "react";
import { Navigate } from 'react-router-dom';
import "./login.css";
import restaiLogo from '../../../assets/img/restai-logo.png';
import { AuthContext } from '../../common/AuthProvider.js';

function Login() {
  const { checkAuth, login } = useContext(AuthContext);
  const [inputUsername, setInputUsername] = useState("");
  const [inputPassword, setInputPassword] = useState("");
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    login(inputUsername, inputPassword)
    await delay(500);
    setShow(true);
    setLoading(false);
  };


  //const handlePassword = () => { };

  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  return !checkAuth() ? (
    <>
      <div className="sign-in__wrapper">
        <div className="sign-in__backdrop"></div>
        <Form className="shadow p-4 bg-white rounded" onSubmit={handleSubmit}>
          <img
            className="img-thumbnail mx-auto d-block mb-2"
            src={restaiLogo}
            alt="logo"
          />
          <div className="h4 mb-2 text-center">LOGIN</div>
          {show ? (
            <Alert
              className="mb-2"
              variant="danger"
              onClose={() => setShow(false)}
              dismissible
            >
              Incorrect username or password.
            </Alert>
          ) : (
            <div />
          )}
          <Form.Group className="mb-2" controlId="username">
            <Form.Label>Username</Form.Label>
            <Form.Control
              type="text"
              value={inputUsername}
              placeholder="Username"
              onChange={(e) => setInputUsername(e.target.value)}
              required
            />
          </Form.Group>
          <Form.Group className="mb-2" controlId="password">
            <Form.Label>Password</Form.Label>
            <Form.Control
              type="password"
              value={inputPassword}
              placeholder="Password"
              onChange={(e) => setInputPassword(e.target.value)}
              required
            />
          </Form.Group>
          <Form.Group className="mb-2" controlId="checkbox">
            <Form.Check type="checkbox" label="Remember me" />
          </Form.Group>
          {!loading ? (
            <Button className="w-100" variant="primary" type="submit">
              Log In
            </Button>
          ) : (
            <Button className="w-100" variant="primary" type="submit" disabled>
              Logging In...
            </Button>
          )}
          {/*           <div className="d-grid justify-content-end">
            <Button
              className="text-muted px-0"
              variant="link"
              onClick={handlePassword}
            >
              Forgot password?
            </Button>
          </div> */}
        </Form>
      </div>
    </>
  ) : (
    <Navigate to="/" />
  );
}

export default Login;