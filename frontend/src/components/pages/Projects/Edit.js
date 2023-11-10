import CustomNavBar from '../../common/navBar.js'
import Container from 'react-bootstrap/Container';
import Row from 'react-bootstrap/Row';
import Form from 'react-bootstrap/Form';
import Col from 'react-bootstrap/Col';
import Button from 'react-bootstrap/Button';
import Alert from 'react-bootstrap/Alert';

import React, { useState, useEffect, useRef } from "react";
import { useParams } from "react-router-dom";

function Edit() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [data, setData] = useState({ projects: [] });
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const [error, setError] = useState([]);
  const systemForm = useRef(null)
  const llmForm = useRef(null)
  var { projectName } = useParams();

  const fetchProject = (projectName) => {
    return fetch(url + "/projects/" + projectName)
      .then((res) => res.json())
      .then((d) => {
        setData(d)
        llmForm.current.value = d.llm
      }
      ).catch(err => {
        setError([...error, { "functionName": "fetchProject", "error": err.toString() }]);
      });
  }

  const fetchInfo = () => {
    return fetch(url + "/info")
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
      headers: new Headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({
        "name": projectName,
        "llm": llmForm.current.value,
        "system": systemForm.current.value
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
    fetchProject(projectName);
    fetchInfo();
  }, [projectName]);


  return (
    <>
      <CustomNavBar />
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
          <Button variant="dark" type="submit" className="mb-2">
            Submit
          </Button>
        </Form>
      </Container>
    </>
  );
}

export default Edit;