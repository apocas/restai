import { Container, Row, Form, InputGroup, Col, Card, Button, Spinner, Alert } from 'react-bootstrap';
import { useParams } from "react-router-dom";
import React, { useState, useEffect, useRef, useContext } from "react";
import { AuthContext } from '../../common/AuthProvider.js';

function Question() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  var { projectName } = useParams();
  const systemForm = useRef(null);
  const questionForm = useRef(null);
  const scoreForm = useRef(null);
  const kForm = useRef(null);
  const [answers, setAnswers] = useState([]);
  const [canSubmit, setCanSubmit] = useState(true);
  const [data, setData] = useState({ projects: [] });
  const [error, setError] = useState([]);
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth();

  const onSubmitHandler = (event) => {
    event.preventDefault();

    var system = systemForm.current.value;
    var question = questionForm.current.value;
    var k = parseInt(kForm.current.value);
    var score = parseFloat(scoreForm.current.value);

    var body = {};
    var submit = false;
    if (system === "" && question !== "") {
      body = {
        "question": question,
        "k": k,
        "score": score
      }
      submit = true;
    } else if (system !== "" && question !== "") {
      body = {
        "question": question,
        "system": system,
        "k": k,
        "score": score
      }
      submit = true;
    }

    if (submit && canSubmit) {
      setCanSubmit(false);
      setAnswers([...answers, { question: question, answer: null }]);
      fetch(url + "/projects/" + projectName + "/question", {
        method: 'POST',
        headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + user.basicAuth }),
        body: JSON.stringify(body),
      })
        .then(response => response.json())
        .then((response) => {
          setAnswers([...answers, { question: question, answer: response.answer }]);
          questionForm.current.value = "";
          setCanSubmit(true);
        }).catch(err => {
          setError([...error, { "functionName": "onSubmitHandler", "error": err.toString() }]);
          setAnswers([...answers, { question: question, answer: "Error, something went wrong with my transistors." }]);
          setCanSubmit(true);
        });
    }
  }

  const fetchProject = (projectName) => {
    return fetch(url + "/projects/" + projectName, { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => setData(d)
      ).catch(err => {
        setError([...error, { "functionName": "fetchProject", "error": err.toString() }]);
      });
  }

  useEffect(() => {
    document.title = 'RestAI  Question ' + projectName;
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
        <h1>Question {projectName}</h1>
        <Form onSubmit={onSubmitHandler}>
          <Row>
            <Col sm={12}>
              <InputGroup>
                <InputGroup.Text>System</InputGroup.Text>
                <Form.Control ref={systemForm} rows="5" as="textarea" aria-label="With textarea" defaultValue={data.system ? data.system : ""} />
              </InputGroup>
            </Col>
            {answers.length > 0 &&
              <Col sm={12}>
                <Card>
                  <Card.Header>Results</Card.Header>
                  <Card.Body>
                    {
                      answers.map((answer, index) => {
                        return (answer.answer != null ?
                          <div className='lineBreaks' key={index} style={index === 0 ? { marginTop: "0px" } : { marginTop: "10px" }}>
                            <span className='highlight'>QUESTION:</span> {answer.question} <br />
                            🤖<span className='highlight'>ANSWER:</span> {answer.answer}
                            <hr />
                          </div>
                          :
                          <div className='lineBreaks' key={index} style={index === 0 ? { marginTop: "0px" } : { marginTop: "10px" }}>
                            <span className='highlight'>QUESTION:</span> {answer.question} <br />
                            🤖<span className='highlight'>ANSWER:</span> <Spinner animation="grow" size="sm" />
                            <hr />
                          </div>
                        )
                      })
                    }
                  </Card.Body>
                </Card>
              </Col>
            }
          </Row>
          <Row style={{ marginTop: "20px" }}>
            <Col sm={12}>
              <InputGroup>
                <InputGroup.Text>Question</InputGroup.Text>
                <Form.Control ref={questionForm} rows="5" as="textarea" aria-label="With textarea" />
              </InputGroup>
            </Col>
          </Row>
          <Row style={{ marginTop: "20px" }}>
            <Col sm={6}>
              <InputGroup>
                <InputGroup.Text>Score Threshold</InputGroup.Text>
                <Form.Control ref={scoreForm} defaultValue={0.3} />
              </InputGroup>
            </Col>
            <Col sm={6}>
              <InputGroup>
                <InputGroup.Text>k</InputGroup.Text>
                <Form.Control ref={kForm} defaultValue={4} />
              </InputGroup>
            </Col>
          </Row>
          <Row style={{ marginTop: "20px" }}>
            <Col sm={10}>
            </Col>
            <Col sm={2}>
              <div className="d-grid gap-2">
                <Button variant="dark" type="submit" size="lg">
                  {
                    canSubmit ? <span>Ask</span> : <Spinner animation="border" />
                  }
                </Button>
              </div>
            </Col>
          </Row>
        </Form>
      </Container>
    </>
  );
}

export default Question;