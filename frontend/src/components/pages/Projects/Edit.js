import CustomNavBar from '../../common/navBar.js'
import Container from 'react-bootstrap/Container';
import Row from 'react-bootstrap/Row';
import Form from 'react-bootstrap/Form';
import Col from 'react-bootstrap/Col';
import Button from 'react-bootstrap/Button';

import React, { useState, useEffect, useRef } from "react";

function Edit() {

  const url = "";
  const [setData] = useState({ projects: [] });
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const projectNameForm = useRef(null)
  const systemForm = useRef(null)
  const llmForm = useRef(null)

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
    fetch(url + "/projects/" + projectNameForm.current.value, {
      method: 'PATCH',
      headers: new Headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        "name": projectNameForm.current.value,
        "llm": llmForm.current.value,
        "system": systemForm.current.value
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
          <h1>Edit Project</h1>
          <Form onSubmit={onSubmitHandler}>
            <Row className="mb-3">
              <Form.Group as={Col} controlId="formGridProjectName">
                <Form.Label>Project Name</Form.Label>
                <Form.Control ref={projectNameForm} />
              </Form.Group>

              <Form.Group as={Col} controlId="formGridSystem">
                <Form.Label>System Message</Form.Label>
                <Form.Control ref={systemForm} />
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
      </Container>
    </>
  );
}

export default Edit;