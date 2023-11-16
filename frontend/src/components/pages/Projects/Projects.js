import { Container, Table, Row, Form, Col, Button, Alert } from 'react-bootstrap';
import { NavLink } from "react-router-dom";
import React, { useState, useEffect, useRef, useContext } from "react";
import { AuthContext } from '../../common/AuthProvider.js';

function Projects() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [data, setData] = useState([]);
  const [users, setUsers] = useState({ "teste": [] });
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const [error, setError] = useState([]);
  const projectNameForm = useRef(null)
  const systemForm = useRef(null)
  const embbeddingForm = useRef(null)
  const llmForm = useRef(null)
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth();

  const handleDeleteClick = (projectName) => {
    alert(projectName);
    fetch(url + "/projects/" + projectName, { method: 'DELETE', headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then(() => fetchProjects()
      ).catch(err => {
        setError([...error, { "functionName": "handleDeleteClick", "error": err.toString() }]);
      });
  }

  const fetchProjects = () => {
    return fetch(url + "/projects", { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => {
        setData(d)
        if (user.admin)
          fetchUsers(d);
      }
      ).catch(err => {
        setError([...error, { "functionName": "fetchProjects", "error": err.toString() }]);
      });
  }

  const fetchInfo = () => {
    return fetch(url + "/info", { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => setInfo(d)
      ).catch(err => {
        setError([...error, { "functionName": "fetchInfo", "error": err.toString() }]);
      });
  }

  const fetchUsers = (data) => {
    return fetch(url + "/users", { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => {
        var arr = {};
        for (let i = 0; i < data.length; i++) {
          arr[data[i].name] = []
          for (let j = 0; j < d.length; j++) {
            for (let z = 0; z < d[j].projects.length; z++) {
              if (data[i].name == d[j].projects[z].name)
                arr[data[i].name].push(d[j].username);
            }
          }
        }
        setUsers(arr)
      }
      ).catch(err => {
        setError([...error, { "functionName": "fetchUsers", "error": err.toString() }]);
      });
  }

  // TODO: response handling
  const onSubmitHandler = (event) => {
    event.preventDefault();
    fetch(url + "/projects", {
      method: 'POST',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + user.basicAuth }),
      body: JSON.stringify({
        "name": projectNameForm.current.value,
        "embeddings": embbeddingForm.current.value,
        "llm": llmForm.current.value,
        "system": systemForm.current.value
      }),
    })
      .then(response => response.json())
      .then(() => fetchProjects()
      ).catch(err => {
        setError([...error, { "functionName": "onSubmitHandler", "error": err.toString() }]);
      });

  }

  useEffect(() => {
    document.title = 'RestAI Projects';
    fetchProjects();
    fetchInfo();
  }, []);

  return (
    <>
      {error.length > 0 &&
        <Alert variant="danger">
          {JSON.stringify(error)}
        </Alert>
      }
      <Container style={{ marginTop: "20px" }}>
        <Row>
          <h1>Projects</h1>
          <Table striped bordered hover responsive>
            <thead>
              <tr>
                <th>#</th>
                <th>Project Name</th>
                <th>Actions</th>
                {user.admin &&
                  <th>Used by</th>
                }
              </tr>
            </thead>
            <tbody>
              {
                data.map((project, index) => {
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
                      {
                        user.admin &&
                        <td>
                          {typeof users[project.name] !== "undefined" && (
                            users[project.name].map((user, index) => {
                              if (users[project.name].length - 1 === index)
                                return <NavLink key={index} to={"/users/" + user}>{user}</NavLink>
                              return <NavLink key={index} to={"/users/" + user}>{user + ", "}</NavLink>
                            })
                          )
                          }
                        </td>
                      }
                    </tr>
                  )
                })
              }
            </tbody>
          </Table>
        </Row>
        <Row>
          <h1>Create Project</h1>
          <Form onSubmit={onSubmitHandler}>
            <Row className="mb-3">
              <Form.Group as={Col} controlId="formGridProjectName">
                <Form.Label>Project Name</Form.Label>
                <Form.Control ref={projectNameForm} />
              </Form.Group>
              <Form.Group as={Col} controlId="formGridEmbeddings">
                <Form.Label>Embeddings</Form.Label>
                <Form.Select ref={embbeddingForm} defaultValue="Choose...">
                  <option>Choose...</option>
                  {
                    info.embeddings.map((embbedding, index) => {
                      return (
                        <option key={index}>{embbedding}</option>
                      )
                    }
                    )
                  }
                </Form.Select>
              </Form.Group>

              <Form.Group as={Col} controlId="formGridLLM">
                <Form.Label>LLM</Form.Label>
                <Form.Select ref={llmForm} defaultValue="Choose...">
                  <option>Choose...</option>
                  {
                    info.llms.map((llm, index) => {
                      return (
                        <option key={index}>{llm}</option>
                      )
                    }
                    )
                  }
                </Form.Select>
              </Form.Group>
            </Row>
            <Row className="mb-3">
              <Form.Group as={Col} controlId="formGridSystem">
                <Form.Label>System Message</Form.Label>
                <Form.Control ref={systemForm} rows="2" as="textarea" />
              </Form.Group>
            </Row>
            <Button variant="dark" type="submit" className="mb-2">
              Submit
            </Button>
          </Form>
        </Row>
      </Container>
    </>
  );
}

export default Projects;