import { Container, Row, Form, Col, Button, Alert, InputGroup } from 'react-bootstrap';
import React, { useState, useEffect, useRef, useContext } from "react";
import { useParams } from "react-router-dom";
import { AuthContext } from '../../common/AuthProvider.js';

function Edit() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [data, setData] = useState({ projects: [] });
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const [error, setError] = useState([]);
  const systemForm = useRef(null)
  const scoreForm = useRef(null);
  const kForm = useRef(null);
  const censorshipForm = useRef(null)
  const llmForm = useRef(null)
  const sandboxedForm = useRef(null)
  var { projectName } = useParams();
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth();

  const fetchProject = (projectName) => {
    return fetch(url + "/projects/" + projectName, { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => {
        setData(d)
        llmForm.current.value = d.llm
        sandboxedForm.current.checked = d.sandboxed
      }
      ).catch(err => {
        setError([...error, { "functionName": "fetchProject", "error": err.toString() }]);
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

  // TODO: response handling
  const onSubmitHandler = (event) => {
    event.preventDefault();
    fetch(url + "/projects/" + projectName, {
      method: 'PATCH',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + user.basicAuth }),
      body: JSON.stringify({
        "name": projectName,
        "llm": llmForm.current.value,
        "system": systemForm.current.value,
        "sandboxed": sandboxedForm.current.checked,
        "censorship": censorshipForm.current.value,
        "score": parseFloat(scoreForm.current.value),
        "k": parseInt(kForm.current.value),
      }),
    })
      .then(response => response.json())
      .then(() => fetchProject(projectName)
      ).catch(err => {
        setError([...error, { "functionName": "onSubmitHandler", "error": err.toString() }]);
      });

  }

  useEffect(() => {
    document.title = 'RestAI Projects';
    fetchInfo();
    fetchProject(projectName);
  }, [projectName]);


  return (
    <>
      {error.length > 0 &&
        <Alert variant="danger">
          {JSON.stringify(error)}
        </Alert>
      }
      <Container style={{ marginTop: "20px" }}>
        <h1>Edit Project {projectName}</h1>
        <Form onSubmit={onSubmitHandler}>
          <Row className="mb-3">
            <Form.Group as={Col} controlId="formGridLLM">
              <Form.Label>LLM</Form.Label>
              <Form.Select ref={llmForm}>
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
              <Form.Control rows="2" as="textarea" ref={systemForm} defaultValue={data.system ? data.system : ""} />
            </Form.Group>
          </Row>
          <hr />
          <Row className="mb-3">
            <Form.Group as={Col} controlId="formGridCensorship">
            <Form.Check ref={sandboxedForm} type="checkbox" label="Sandboxed" /> <Form.Label>Censorship Message</Form.Label>
              <Form.Control rows="2" as="textarea" ref={censorshipForm} defaultValue={data.censorship ? data.censorship : ""} />
            </Form.Group>
          </Row>
          <hr />
          <Row>
            <Col sm={6}>
              <InputGroup>
                <InputGroup.Text>Score Threshold</InputGroup.Text>
                <Form.Control ref={scoreForm} defaultValue={data.score} />
              </InputGroup>
            </Col>
            <Col sm={6}>
              <InputGroup>
                <InputGroup.Text>k</InputGroup.Text>
                <Form.Control ref={kForm} defaultValue={data.k} />
              </InputGroup>
            </Col>
          </Row>
          <Button variant="dark" type="submit" className="mb-2" style={{ marginTop: "20px" }}>
            Save
          </Button>
        </Form>
      </Container>
    </>
  );
}

export default Edit;