import CustomNavBar from '../../common/navBar.js'
import Container from 'react-bootstrap/Container';
import Table from 'react-bootstrap/Table';
import Row from 'react-bootstrap/Row';
import Form from 'react-bootstrap/Form';
import Col from 'react-bootstrap/Col';
import Button from 'react-bootstrap/Button';
import { NavLink } from "react-router-dom";

import React, { useState, useEffect, useRef } from "react";

function Projects() {

  const url = "";
  const [data, setData] = useState({ projects: [] });
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const projectNameForm = useRef(null)
  const embbeddingForm = useRef(null)
  const llmForm = useRef(null)

  // TODO: error handling
  const handleDeleteClick = (projectName) => {
    alert(projectName);
    fetch(url + "/projects/" + projectName, { method: 'DELETE' })
      .then(() => fetchProjects());
  }

  // TODO: error handling
  const fetchProjects = () => {
    return fetch(url + "/projects")
      .then((res) => res.json())
      .then((d) => setData(d))
  }

  // TODO: error handling
  const fetchInfo = () => {
    return fetch(url + "/info")
      .then((res) => res.json())
      .then((d) => setInfo(d))
  }

  // TODO: error handling and response
  const onSubmitHandler = (event) => {
    event.preventDefault();
    fetch(url + "/projects", {
      method: 'POST',
      headers: new Headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        "name": projectNameForm.current.value,
        "embeddings": embbeddingForm.current.value,
        "llm": llmForm.current.value
      }),
    })
      .then(response => response.json())
      .then(() => fetchProjects())

  }

  useEffect(() => {
    document.title = 'RestAI Projects';
    fetchProjects();
    fetchInfo();
  }, []);

  return (
    <>
      <CustomNavBar />
      <Container style={{ marginTop: "20px" }}>
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
                          to={"/projects/" + project}
                        >
                          {project}
                        </NavLink>
                      </td>
                      <td>
                        <NavLink
                          to={"/projects/" + project}
                        >
                          <Button variant="dark">View</Button>{' '}
                        </NavLink>
                        <NavLink
                          to={"/projects/" + project + "/chat"}
                        >
                          <Button variant="dark">Chat</Button>{' '}
                        </NavLink>
                        <NavLink
                          to={"/projects/" + project + "/question"}
                        >
                          <Button variant="dark">Question</Button>{' '}
                        </NavLink>
                        <Button onClick={() => handleDeleteClick(project)} variant="danger">Delete</Button>
                      </td>
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