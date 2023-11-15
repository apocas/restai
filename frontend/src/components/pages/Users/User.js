import { Container, Table, Row, Col, Button, ListGroup, Alert } from 'react-bootstrap';
import { useParams, NavLink } from "react-router-dom";
import React, { useState, useEffect, useContext } from "react";
import { AuthContext } from '../../common/AuthProvider.js';

function User() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [data, setData] = useState({ projects: [] });
  const [error, setError] = useState([]);
  var { username } = useParams();
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth();


  const fetchUser = (username) => {
    return fetch(url + "/user/" + username, { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => setData(d)
      ).catch(err => {
        setError([...error, { "functionName": "fetchUser", "error": err.toString() }]);
      });
  }

  const handleDeleteClick = (projectName) => {
    alert(projectName);
    fetch(url + "/projects/" + projectName, { method: 'DELETE', headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then(() => fetchUser()
      ).catch(err => {
        setError([...error, { "functionName": "handleDeleteClick", "error": err.toString() }]);
      });
  }

  useEffect(() => {
    document.title = 'RestAI User ' + username;
    fetchUser(username);
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
            </ListGroup>
          </Col>
        </Row>
        <Row>
          <h1>Projects</h1>
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
                        <NavLink
                          to={"/projects/" + project.name}
                        >
                          <Button variant="dark">View</Button>{' '}
                        </NavLink>
                        <NavLink
                          to={"/projects/" + project.name + "/edit"}
                        >
                          <Button variant="dark">Edit</Button>{' '}
                        </NavLink>
                        <NavLink
                          to={"/projects/" + project.name + "/chat"}
                        >
                          <Button variant="dark">Chat</Button>{' '}
                        </NavLink>
                        <NavLink
                          to={"/projects/" + project.name + "/question"}
                        >
                          <Button variant="dark">Question</Button>{' '}
                        </NavLink>
                        <Button onClick={() => handleDeleteClick(project.name)} variant="danger">Delete</Button>
                      </td>
                    </tr>
                  )
                })
              }
            </tbody>
          </Table>
        </Row>
      </Container>
    </>
  );
}

export default User;