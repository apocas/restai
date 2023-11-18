import { Container, Row, Form, InputGroup, Col, Card, Button, Spinner, Alert } from 'react-bootstrap';
import { useParams } from "react-router-dom";
import React, { useState, useEffect, useRef, useContext } from "react";
import { AuthContext } from '../../common/AuthProvider.js';

function Chat() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  var { projectName } = useParams();
  const messageForm = useRef(null);
  const scoreForm = useRef(null);
  const kForm = useRef(null);
  const [messages, setMessages] = useState([]);
  const [canSubmit, setCanSubmit] = useState(true);
  const [error, setError] = useState([]);
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth();

  const onSubmitHandler = (event) => {
    event.preventDefault();

    var message = messageForm.current.value;
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
    if (message !== "" && id === "") {
      body = {
        "message": message,
        "k": k,
        "score": score
      }
      submit = true;
    } else if (message !== "" && id !== "") {
      body = {
        "message": message,
        "id": id,
        "k": k,
        "score": score
      }
      submit = true;
    }

    if (submit && canSubmit) {
      setCanSubmit(false);
      setMessages([...messages, { id: id, message: message, response: null }]);
      fetch(url + "/projects/" + projectName + "/chat", {
        method: 'POST',
        headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + user.basicAuth }),
        body: JSON.stringify(body),
      })
        .then(response => response.json())
        .then((response) => {
          setMessages([...messages, { id: response.id, message: message, response: response.response }]);
          messageForm.current.value = "";
          setCanSubmit(true);
        }).catch(err => {
          setError([...error, { "functionName": "onSubmitHandler", "error": err.toString() }]);
          setMessages([...messages, { id: id, message: message, response: "Error, something went wrong with my transistors." }]);
          setCanSubmit(true);
        });
    }
  }

  useEffect(() => {
    document.title = 'RestAI  Chat ' + projectName;
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
                        return (message.response != null ?
                          <div className='lineBreaks' key={index} style={index === 0 ? { marginTop: "0px" } : { marginTop: "10px" }}>
                            <span className='highlight'>MESSAGE:</span> {message.message} <br />
                            🤖<span className='highlight'>RESPONSE:</span> {message.response}
                            <hr />
                          </div>
                          :
                          <div className='lineBreaks' key={index} style={index === 0 ? { marginTop: "0px" } : { marginTop: "10px" }}>
                            <span className='highlight'>MESSAGE:</span> {message.message} <br />
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
                <InputGroup.Text>Score Threshold</InputGroup.Text>
                <Form.Control ref={scoreForm} defaultValue={0.4} />
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