import { Container, Row, Form, Col, Button, Alert } from 'react-bootstrap';
import React, { useState, useEffect, useRef, useContext } from "react";
import { useParams, NavLink } from "react-router-dom";
import { AuthContext } from '../../common/AuthProvider.js';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';

function Edit() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [error, setError] = useState([]);
  const passwordForm = useRef(null)
  const isadminForm = useRef(null)
  const isprivateForm = useRef(null)
  var { username } = useParams();
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth();

  const Link = ({ id, children, title }) => (
    <OverlayTrigger overlay={<Tooltip id={id}>{title}</Tooltip>}>
      <a href="#" style={{ fontSize: "small", margin: "3px" }}>{children}</a>
    </OverlayTrigger>
  );

  // TODO: response handling
  const onSubmitHandler = (event) => {
    event.preventDefault();
    var update = {
      "is_admin": isadminForm.current.checked,
      "is_private": isprivateForm.current.checked
    };
    if (passwordForm.current.value !== "") {
      update.password = passwordForm.current.value
    }

    fetch(url + "/users/" + username, {
      method: 'PATCH',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + user.basicAuth }),
      body: JSON.stringify(update),
    })
      .then(response => response.json())
      .then(response => {
        window.location.href = "/admin/users/" + username;
      })
      .catch(err => {
        setError([...error, { "functionName": "onSubmitHandler", "error": err.toString() }]);
      });

  }

  const fetchUser = (username) => {
    return fetch(url + "/users/" + username, { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => {
        isadminForm.current.checked = d.is_admin
        isprivateForm.current.checked = d.is_private
      }
      ).catch(err => {
        setError([...error, { "functionName": "fetchUser", "error": err.toString() }]);
      });
  }

  useEffect(() => {
    document.title = 'RestAI Users';
    fetchUser(username);
  }, []);


  return (
    <>
      {error.length > 0 &&
        <Alert variant="danger">
          {JSON.stringify(error)}
        </Alert>
      }
      <Container style={{ marginTop: "20px" }}>
        <h1>Edit User {username}</h1>
        <Form onSubmit={onSubmitHandler}>
          <Row className="mb-3">
            <Form.Group as={Col} controlId="formGridUserName">
              <Form.Label>Password</Form.Label>
              <Form.Control type="password" ref={passwordForm} />
            </Form.Group>
            {user.admin &&
              <Form.Group as={Col} controlId="formGridAdmin">
                <Form.Check ref={isadminForm} type="checkbox" label="Admin" />
                <Link title="Admins have access to all projects and can edit all users">ℹ️</Link>
              </Form.Group>
            }
                {user.admin &&
              <Form.Group as={Col} controlId="formGridAdmin">
                <Form.Check ref={isprivateForm} type="checkbox" label="Private models only" />
                <Link title="Can only use private/local models">ℹ️</Link>
              </Form.Group>
            }
          </Row>
          <Button variant="dark" type="submit" className="mb-2">
            Save
          </Button>
          <NavLink to={"/users/" + username} >
              <Button variant="danger" style={{ marginLeft: "10px", marginTop: "-8px" }}>Cancel</Button>{' '}
          </NavLink>
        </Form>
      </Container>
    </>
  );
}

export default Edit;