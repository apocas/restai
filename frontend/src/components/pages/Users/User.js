import { Container, Table, Row, Form, Col, Button, ListGroup, Alert } from 'react-bootstrap';
import { useParams, NavLink } from "react-router-dom";
import React, { useState, useEffect, useContext, useRef } from "react";
import { AuthContext } from '../../common/AuthProvider.js';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';

function User() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const projectForm = useRef(null)
  const [data, setData] = useState({ projects: [] });
  const [projects, setProjects] = useState([]);
  const [error, setError] = useState([]);
  var { username } = useParams();
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth() || { username: null, admin: null };

  const Link = ({ id, children, title }) => (
    <OverlayTrigger overlay={<Tooltip id={id}>{title}</Tooltip>}>
      <a href="#" style={{ fontSize: "small", margin: "3px" }}>{children}</a>
    </OverlayTrigger>
  );

  const fetchUser = (username) => {
    return fetch(url + "/users/" + username, { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => setData(d)
      ).catch(err => {
        setError([...error, { "functionName": "fetchUser", "error": err.toString() }]);
      });
  }

  const fetchProjects = () => {
    return fetch(url + "/projects", { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => setProjects(d)
      ).catch(err => {
        setError([...error, { "functionName": "fetchProjects", "error": err.toString() }]);
      });
  }

  const handleRemoveClick = (projectName) => {
    var projectsi = [];
    for (var i = 0; i < data.projects.length; i++) {
      if (data.projects[i].name !== projectName) {
        projectsi.push(data.projects[i].name);
      }
    }

    fetch(url + "/users/" + username, {
      method: 'PATCH',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + user.basicAuth }),
      body: JSON.stringify({
        "projects": projectsi
      }),
    })
      .then(response => fetchUser(username))
      .catch(err => {
        setError([...error, { "functionName": "onSubmitHandler", "error": err.toString() }]);
      });
  }

  const onSubmitHandler = (event) => {
    event.preventDefault();

    var projectsi = [];
    for (var i = 0; i < data.projects.length; i++) {
      projectsi.push(data.projects[i].name);
    }

    projectsi.push(projectForm.current.value)

    fetch(url + "/users/" + username, {
      method: 'PATCH',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + user.basicAuth }),
      body: JSON.stringify({
        "projects": projectsi
      }),
    })
      .then(response => fetchUser(username))
      .catch(err => {
        setError([...error, { "functionName": "onSubmitHandler", "error": err.toString() }]);
      });
  }

  useEffect(() => {
    document.title = 'RestAI User ' + username;
    fetchUser(username);
    fetchProjects();
  }, [username]);

  return (
    <>
      {error.length > 0 &&
        <Alert variant="danger">
          {JSON.stringify(error)}
        </Alert>
      }
      <Container style={{ marginTop: "20px" }}>
        <Row style={{ marginTop: "20px" }}>
          <Col sm={12}>
            <h1>Status</h1>
            <ListGroup>
              <ListGroup.Item>Id: {data.id}</ListGroup.Item>
              <ListGroup.Item>Username: {data.username}</ListGroup.Item>
              <ListGroup.Item>Projects Count: {data.projects.length}</ListGroup.Item>
              <ListGroup.Item>Admin: {data.is_admin ? (<span>✅</span>) : (<span>❌</span>)}</ListGroup.Item>
            </ListGroup>
          </Col>
        </Row>
        <Row style={{ marginTop: "20px" }}>
          <hr />
          <h1>Projects</h1>
          {user.admin && (
            <Form onSubmit={onSubmitHandler}>
              <Row className="mb-3">
                <Form.Group as={Col} controlId="formGridProjects">
                  <Form.Label>Project<Link title="Allow this user to access this project">ℹ️</Link></Form.Label>
                  <Form.Select ref={projectForm} defaultValue="">
                    <option>Choose...</option>
                    {
                      projects.map((project, index) => {
                        return (
                          <option key={index}>{project.name}</option>
                        )
                      })
                    }
                  </Form.Select>
                </Form.Group>
              </Row>
              <Button variant="dark" type="submit" className="mb-2">
                Add Project
              </Button>
            </Form>
          )}
          <hr />
          <h1>List</h1>
          <Table striped bordered hover responsive>
            <thead>
              <tr>
                <th>#</th>
                <th>Project Name</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {
                data.projects.map((project, index) => {
                  return (
                    <tr key={index}>
                      <td>{index}</td>
                      <td>
                        <NavLink
                          to={"/projects/" + project.name}
                        >
                          {project.name}
                        </NavLink>
                      </td>
                      <td>
                        <Button onClick={() => handleRemoveClick(project.name)} variant="danger">Remove</Button>
                      </td>
                    </tr>
                  )
                })
              }
            </tbody>
          </Table>
        </Row>
      </Container >
    </>
  );
}

export default User;