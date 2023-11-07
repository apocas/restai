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

function Question() {

  const url = "https://ai.ptisp.systems";
  var { projectName } = useParams();
  const systemForm = useRef(null);
  const questionForm = useRef(null);
  const [answers, setAnswers] = useState([]);

  // TODO: error handling and response
  const onSubmitHandler = (event) => {
    event.preventDefault();
    console.log(systemForm.current.value)
    console.log(questionForm.current.value)

    var system = systemForm.current.value;
    var question = questionForm.current.value;

    var body = {};
    var submit = false;
    if (system === "" && question !== "") {
      body = {
        "question": question
      }
      submit = true;
    } else if (system !== "" && question !== "") {
      body = {
        "question": question,
        "system": system
      }
      submit = true;
    }

    if (submit) {
      setAnswers([...answers, { question: question, answer: null }]);
      fetch(url + "/projects/" + projectName + "/question", {
        method: 'POST',
        headers: new Headers({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(body),
      })
        .then(response => response.json())
        .then((response) => {
          setAnswers([...answers, { question: question, answer: response.answer }]);
          systemForm.current.value = "";
          questionForm.current.value = "";
        })
    }
  }

  useEffect(() => {
    document.title = 'RestAI  Question ' + projectName;
  }, [projectName]);

  return (
    <>
      <CustomNavBar />
      <Container style={{ marginTop: "20px" }}>
        <h1>Question {projectName}</h1>
        <Form onSubmit={onSubmitHandler}>
          <Row>
            {answers.length > 0 &&
              <Col sm={12}>
                <Card>
                  <Card.Header>Results</Card.Header>
                  <Card.Body>
                    {
                      answers.map((answer, index) => {
                        return (answer.answer != null ?
                          <div key={index} style={index === 0 ? { marginTop: "0px" } : { marginTop: "10px" }}>
                            <span className='highlight'>QUESTION:</span> {answer.question} <br />
                            <span className='highlight'>ANSWER:</span> {answer.answer}
                            <hr />
                          </div>
                          :
                          <div key={index} style={index === 0 ? { marginTop: "0px" } : { marginTop: "10px" }}>
                            <span className='highlight'>QUESTION:</span> {answer.question} <br />
                            <span className='highlight'>ANSWER:</span> <Spinner animation="grow" size="sm" />
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
            <Col sm={6}>
              <InputGroup>
                <InputGroup.Text>System</InputGroup.Text>
                <Form.Control ref={systemForm} rows="5" as="textarea" aria-label="With textarea" />
              </InputGroup>
            </Col>
            <Col sm={6}>
              <InputGroup>
                <InputGroup.Text>Question</InputGroup.Text>
                <Form.Control ref={questionForm} rows="5" as="textarea" aria-label="With textarea" />
              </InputGroup>
            </Col>
          </Row>
          <Row style={{ marginTop: "20px" }}>
            <Col sm={10}>
            </Col>
            <Col sm={2}>
              <div className="d-grid gap-2">
                <Button variant="dark" type="submit" size="lg">
                  Ask
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