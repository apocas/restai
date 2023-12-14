import { Container, Table, Row, Form, Col, Button, Alert } from 'react-bootstrap';
import { NavLink } from "react-router-dom";
import React, { useState, useEffect, useRef, useContext } from "react";
import { AuthContext } from '../../common/AuthProvider.js';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';

function Projects() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [data, setData] = useState([]);
  const [displayData, setDisplayData] = useState([]);
  const [users, setUsers] = useState({ "teste": [] });
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const [error, setError] = useState([]);
  const projectNameForm = useRef(null)
  const embbeddingForm = useRef(null)
  const llmForm = useRef(null)
  const vectorForm = useRef(null)
  const embbeddingFilter = useRef(null)
  const llmFilter = useRef(null)
  const vectorFilter = useRef(null)
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth();

  const Link = ({ id, children, title }) => (
    <OverlayTrigger overlay={<Tooltip id={id}>{title}</Tooltip>}>
      <a href="#" style={{ fontSize: "small", margin: "3px" }}>{children}</a>
    </OverlayTrigger>
  );

  const fetchProjects = () => {
    return fetch(url + "/projects", { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => {
        setData(d)
        setDisplayData(d)
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
              if (data[i].name === d[j].projects[z].name)
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

  const handleFilterChange = () => {
    var newData = [];
    var embFilterValue = embbeddingFilter.current.value;
    var llmFilterValue = llmFilter.current.value;
    var vectorFilterValue = vectorFilter.current.value;
    if (embFilterValue === "All" && llmFilterValue === "All" && vectorFilterValue === "All") {
      newData = [...data];
      setDisplayData(newData);
    } else {
      newData = data.filter(element => element.embeddings === embFilterValue || element.llm === llmFilterValue || element.vectorstore === vectorFilterValue)
      setDisplayData(newData);
    }
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
        "vectorstore": vectorForm.current.value,
      }),
    })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            setError([...error, { "functionName": "onSubmitHandler", "error": data.detail }]);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
      .then(() => {
        //fetchProjects()
        window.location = "/admin/projects/" + projectNameForm.current.value + "/edit"
      }).catch(err => {
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
        <h1>Projects</h1>
        <Row style={{ marginBottom: "10px" }}>
          <h5>Filters</h5>

          <Form.Group as={Col} controlId="formGridLLM">
            <Form.Label>LLM</Form.Label>
            <Form.Select ref={llmFilter} onClick={handleFilterChange} defaultValue="All">
              <option>All</option>
              {
                info.llms.map((llm, index) => {
                  return (
                    <option key={index}>{llm.name}</option>
                  )
                }
                )
              }
            </Form.Select>
          </Form.Group>

          <Form.Group as={Col} controlId="formGridEmbeddings">
            <Form.Label>Embeddings<Link title="Model used to compute embeddings">ℹ️</Link></Form.Label>
            <Form.Select ref={embbeddingFilter} onClick={handleFilterChange} defaultValue="All">
              <option>All</option>
              {
                info.embeddings.map((embbedding, index) => {
                  return (
                    <option key={index}>{embbedding.name}</option>
                  )
                }
                )
              }
            </Form.Select>
          </Form.Group>

          <Form.Group as={Col} controlId="formGridVector">
            <Form.Label>Vectorstore<Link title="Chroma is monolithic and only recommended for testing. Redis is distributed.">ℹ️</Link></Form.Label>
            <Form.Select ref={vectorFilter} onClick={handleFilterChange} defaultValue="All">
              <option>All</option>
              <option>chroma</option>
              <option>redis</option>
            </Form.Select>
          </Form.Group>
        </Row>
        <Row>
          <Table striped bordered hover responsive>
            <thead>
              <tr>
                <th>#</th>
                <th>Project Name</th>
                <th>Model</th>
                <th>Actions</th>
                <th>Inference<Link title="Chat has memory. Question doesn't">ℹ️</Link></th>
                {user.admin &&
                  <th>Used by</th>
                }
              </tr>
            </thead>
            <tbody>
              {
                displayData.map((project, index) => {
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
                        {project.llm}
                      </td>
                      <td>
                        <NavLink
                          to={"/projects/" + project.name}
                        >
                          <Button variant="dark">View</Button>{' '}
                        </NavLink>
                      </td>
                      <td>
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
        <hr />
        <Row>
          <h1>Create Project</h1>
          <Form onSubmit={onSubmitHandler}>
            <Row className="mb-3">
              <Form.Group as={Col} controlId="formGridProjectName">
                <Form.Label>Project Name</Form.Label>
                <Form.Control ref={projectNameForm} />
              </Form.Group>
              <Form.Group as={Col} controlId="formGridEmbeddings">
                <Form.Label>Embeddings<Link title="Model used to compute embeddings">ℹ️</Link></Form.Label>
                <Form.Select ref={embbeddingForm} defaultValue="">
                  <option>Choose...</option>
                  {
                    info.embeddings.map((embbedding, index) => {
                      return (
                        <option key={index}>{embbedding.name}</option>
                      )
                    }
                    )
                  }
                </Form.Select>
              </Form.Group>

              <Form.Group as={Col} controlId="formGridLLM">
                <Form.Label>LLM</Form.Label>
                <Form.Select ref={llmForm} defaultValue="">
                  <option>Choose...</option>
                  {
                    info.llms.map((llm, index) => {
                      return (
                        <option key={index}>{llm.name}</option>
                      )
                    }
                    )
                  }
                </Form.Select>
              </Form.Group>

              <Form.Group as={Col} controlId="formGridVector">
                <Form.Label>Vectorstore<Link title="Chroma is monolithic and only recommended for testing. Redis is distributed.">ℹ️</Link></Form.Label>
                <Form.Select ref={vectorForm} defaultValue="chroma">
                  <option>chroma</option>
                  <option>redis</option>
                </Form.Select>
              </Form.Group>
            </Row>
            <Button variant="dark" type="submit" className="mb-2">
              Create
            </Button>
          </Form>
        </Row>
      </Container >
    </>
  );
}

export default Projects;