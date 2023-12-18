import { Container, Table, Row, Form, Col, Button, Alert } from 'react-bootstrap';
import { NavLink, Navigate } from "react-router-dom";
import React, { useState, useEffect, useRef, useContext } from "react";
import { AuthContext } from '../../common/AuthProvider.js';

function Users() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [data, setData] = useState([]);
  const [error, setError] = useState([]);
  const usernameForm = useRef(null)
  const passwordForm = useRef(null)
  const isadminForm = useRef(null)
  const isprivateForm = useRef(null)
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth() || { username: null, admin: null };

  const handleDeleteClick = (username) => {
    if(window.confirm("Delete " + username + "?")) {
      fetch(url + "/users/" + username, {
        method: 'DELETE',
        headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth })
      }).then(() => fetchUsers()
      ).catch(err => {
        setError([...error, { "functionName": "handleDeleteClick", "error": err.toString() }]);
      });
    }
  }

  const fetchUsers = () => {
    return fetch(url + "/users", { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => setData(d)
      ).catch(err => {
        setError([...error, { "functionName": "fetchUsers", "error": err.toString() }]);
      });
  }

  // TODO: response handling
  const onSubmitHandler = (event) => {
    event.preventDefault();
    fetch(url + "/users", {
      method: 'POST',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + user.basicAuth }),
      body: JSON.stringify({
        "username": usernameForm.current.value,
        "password": passwordForm.current.value,
        "is_admin": isadminForm.current.checked,
        "is_private": isprivateForm.current.checked,
      }),
    })
      .then(response => response.json())
      .then(() => fetchUsers()
      ).catch(err => {
        setError([...error, { "functionName": "onSubmitHandler", "error": err.toString() }]);
      });

  }

  useEffect(() => {
    document.title = 'RestAI Users';
    fetchUsers();
  }, []);

  return user.admin ? (
    <>
      {error.length > 0 &&
        <Alert variant="danger">
          {JSON.stringify(error)}
        </Alert>
      }
      <Container style={{ marginTop: "20px" }}>
        <Row>
          <h1>Users</h1>
          <Table striped bordered hover responsive>
            <thead>
              <tr>
                <th>#</th>
                <th>Username</th>
                <th>Type</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {
                data.map((user, index) => {
                  return (
                    <tr key={index}>
                      <td>{index}</td>
                      <td>
                        <NavLink
                          to={"/users/" + user.username}
                        >
                          {user.username}
                        </NavLink>
                      </td>
                      <td>
                        {user.is_admin ? "Admin" : "User"}
                      </td>
                      <td>
                        <NavLink
                          to={"/users/" + user.username}
                        >
                          <Button variant="dark">View</Button>{' '}
                        </NavLink>
                        <NavLink
                          to={"/users/" + user.username + "/edit"}
                        >
                          <Button variant="dark">Edit</Button>{' '}
                        </NavLink>
                        <Button onClick={() => handleDeleteClick(user.username)} variant="danger">Delete</Button>
                      </td>
                    </tr>
                  )
                })
              }
            </tbody>
          </Table>
        </Row>
        <hr />
        <Row>
          <h1>Create User</h1>
          <Form onSubmit={onSubmitHandler}>
            <Row className="mb-3">
              <Form.Group as={Col} controlId="formGridUserName">
                <Form.Label>Username</Form.Label>
                <Form.Control ref={usernameForm} />
              </Form.Group>
              <Form.Group as={Col} controlId="formGridUserName">
                <Form.Label>Password</Form.Label>
                <Form.Control ref={passwordForm} />
              </Form.Group>
              <Form.Group as={Col} controlId="formGridAdmin">
                <Form.Check ref={isadminForm} type="checkbox" label="Admin" />
              </Form.Group>
              <Form.Group as={Col} controlId="formGridPrivate">
                <Form.Check ref={isprivateForm} type="checkbox" label="Private only models" />
              </Form.Group>
            </Row>
            <Button variant="dark" type="submit" className="mb-2">
              Submit
            </Button>
          </Form>
        </Row>
      </Container>
    </>
  ) : (
    <Navigate to="/" />
  );
}

export default Users;