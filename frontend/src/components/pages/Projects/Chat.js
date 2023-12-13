import { Container, Row, Form, InputGroup, Col, Card, Button, Spinner, Alert, Accordion } from 'react-bootstrap';
import { useAccordionButton } from 'react-bootstrap/AccordionButton';
import { useParams } from "react-router-dom";
import React, { useState, useEffect, useRef, useContext } from "react";
import { AuthContext } from '../../common/AuthProvider.js';
import ReactJson from '@microlink/react-json-view';
import OverlayTrigger from 'react-bootstrap/OverlayTrigger';
import Tooltip from 'react-bootstrap/Tooltip';

function Chat() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  var { projectName } = useParams();
  const messageForm = useRef(null);
  const scoreForm = useRef(null);
  const kForm = useRef(null);
  const [messages, setMessages] = useState([]);
  const [canSubmit, setCanSubmit] = useState(true);
  const [data, setData] = useState({ projects: [] });
  const [error, setError] = useState([]);
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth();

  const Link = ({ id, children, title }) => (
    <OverlayTrigger overlay={<Tooltip id={id}>{title}</Tooltip>}>
      <a href="#" style={{ fontSize: "small", margin: "3px" }}>{children}</a>
    </OverlayTrigger>
  );

  function CustomToggle({ children, eventKey }) {
    const decoratedOnClick = useAccordionButton(eventKey, () =>
      console.log('totally custom!'),
    );
  
    return (
      <span
        onClick={decoratedOnClick} style={{ cursor: 'pointer' }}
      >
        {children}
      </span>
    );
  }

  const onSubmitHandler = (event) => {
    event.preventDefault();

    var question = messageForm.current.value;
    var id = "";
    var k = parseInt(kForm.current.value);
    var score = parseFloat(scoreForm.current.value);

    if (messages.length === 0) {
      id = "";
    } else {
      id = messages[messages.length - 1].id
    }

    var body = {};
    var submit = false;
    if (question !== "" && id === "") {
      body = {
        "question": question,
        "k": k,
        "score": score
      }
      submit = true;
    } else if (question !== "" && id !== "") {
      body = {
        "question": question,
        "id": id,
        "k": k,
        "score": score
      }
      submit = true;
    }

    if (submit && canSubmit) {
      setCanSubmit(false);
      setMessages([...messages, { id: id, question: question, answer: null, sources: [] }]);
      fetch(url + "/projects/" + projectName + "/chat", {
        method: 'POST',
        headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + user.basicAuth }),
        body: JSON.stringify(body),
      })
        .then(response => response.json())
        .then((response) => {
          setMessages([...messages, { id: response.id, question: response.question, answer: response.answer, sources: response.sources }]);
          messageForm.current.value = "";
          setCanSubmit(true);
        }).catch(err => {
          setError([...error, { "functionName": "onSubmitHandler", "error": err.toString() }]);
          setMessages([...messages, { id: id, question: question, answer: "Error, something went wrong with my transistors.", sources: [] }]);
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
    document.title = 'RestAI  Chat ' + projectName;
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
        <h1>Chat {projectName}</h1>
        <Form onSubmit={onSubmitHandler}>
          <Row>
            {messages.length > 0 &&
              <Col sm={12}>
                <Card>
                  <Card.Header>Results</Card.Header>
                  <Card.Body>
                    {
                      messages.map((message, index) => {
                        return (message.answer != null ?
                          <div className='lineBreaks' key={index} style={index === 0 ? { marginTop: "0px" } : { marginTop: "10px" }}>
                            🧑<span className='highlight'>MESSAGE:</span> {message.question} <br />
                            🤖<span className='highlight'>RESPONSE:</span> {message.answer}
                            <Accordion>
                              <Row style={{ textAlign: "right", marginBottom: "0px" }}>
                                <CustomToggle eventKey="0">Details</CustomToggle>
                              </Row>
                              <Accordion.Collapse eventKey="0">
                                <Card.Body><ReactJson src={message} enableClipboard={false}/></Card.Body>
                              </Accordion.Collapse>
                            </Accordion>
                            <hr />
                          </div>
                          :
                          <div className='lineBreaks' key={index} style={index === 0 ? { marginTop: "0px" } : { marginTop: "10px" }}>
                            🧑<span className='highlight'>MESSAGE:</span> {message.question} <br />
                            🤖<span className='highlight'>RESPONSE:</span> <Spinner animation="grow" size="sm" />
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
                <InputGroup.Text>Message</InputGroup.Text>
                <Form.Control ref={messageForm} rows="5" as="textarea" aria-label="With textarea" />
              </InputGroup>
            </Col>
          </Row>
          <Row style={{ marginTop: "20px" }}>
            <Col sm={6}>
              <InputGroup>
                <InputGroup.Text>Score Threshold<Link title="Value between 0 and 1. Larger equals more similarity required from embeddings during retrieval process. Smaller less similarity required.">ℹ️</Link></InputGroup.Text>
                <Form.Control ref={scoreForm} defaultValue={data.score} />
              </InputGroup>
            </Col>
            <Col sm={6}>
              <InputGroup>
                <InputGroup.Text>k<Link title="Bigger value slower results but more data from embeddings will be used.">ℹ️</Link></InputGroup.Text>
                <Form.Control ref={kForm} defaultValue={data.k} />
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
                    canSubmit ? <span>Chat</span> : <Spinner animation="border" />
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

export default Chat;