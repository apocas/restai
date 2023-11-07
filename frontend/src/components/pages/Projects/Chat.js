import CustomNavBar from '../../common/navBar.js'
import Container from 'react-bootstrap/Container';
import Row from 'react-bootstrap/Row';
import Form from 'react-bootstrap/Form';
import InputGroup from 'react-bootstrap/InputGroup';
import Col from 'react-bootstrap/Col';
import Card from 'react-bootstrap/Card';
import Button from 'react-bootstrap/Button';
import Spinner from 'react-bootstrap/Spinner';
import { useParams } from "react-router-dom";


import React, { useState, useEffect, useRef } from "react";

function Chat() {

  const url = "https://ai.ptisp.systems";
  var { projectName } = useParams();
  const messageForm = useRef(null);
  const [messages, setMessages] = useState([]);

  // TODO: error handling and response
  const onSubmitHandler = (event) => {
    event.preventDefault();

    var message = messageForm.current.value;
    var id = "";

    if (messages.length === 0) {
      id = "";
    } else {
      id = messages[messages.length - 1].id
    }

    var body = {};
    var submit = false;
    if (message !== "" && id === "") {
      body = {
        "message": message
      }
      submit = true;
    } else if (message !== "" && id !== "") {
      body = {
        "message": message,
        "id": id
      }
      submit = true;
    }

    if (submit) {
      setMessages([...messages, { id: id, message: message, response: null }]);
      fetch(url + "/projects/" + projectName + "/chat", {
        method: 'POST',
        headers: new Headers({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(body),
      })
        .then(response => response.json())
        .then((response) => {
          setMessages([...messages, { id: response.id, message: message, response: response.response }]);
          messageForm.current.value = "";
        })
    }
  }

  useEffect(() => {
    document.title = 'RestAI  Chat ' + projectName;
  }, [projectName]);

  return (
    <>
      <CustomNavBar />
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
                          <div key={index} style={index === 0 ? { marginTop: "0px" } : { marginTop: "10px" }}>
                            <span className='highlight'>MESSAGE:</span> {message.message} <br />
                            <span className='highlight'>RESPONSE:</span> {message.response}
                            <hr />
                          </div>
                          :
                          <div key={index} style={index === 0 ? { marginTop: "0px" } : { marginTop: "10px" }}>
                            <span className='highlight'>MESSAGE:</span> {message.message} <br />
                            <span className='highlight'>RESPONSE:</span> <Spinner animation="grow" size="sm" />
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
            <Col sm={10}>
            </Col>
            <Col sm={2}>
              <div className="d-grid gap-2">
                <Button variant="dark" type="submit" size="lg">
                  Chat
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