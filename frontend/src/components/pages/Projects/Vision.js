import { Container, Row, Form, InputGroup, Col, Card, Button, Spinner, Alert, Accordion } from 'react-bootstrap';
import { useAccordionButton } from 'react-bootstrap/AccordionButton';
import { useParams } from "react-router-dom";
import React, { useState, useEffect, useRef, useContext } from "react";
import { AuthContext } from '../../common/AuthProvider.js';
import ReactJson from '@microlink/react-json-view';
import ModalImage from "react-modal-image";
import NoImage from '../../../assets/img/no-image.jpg'

function Vision() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  var { projectName } = useParams();
  const questionForm = useRef(null);
  const urlForm = useRef(null);
  const uploadForm = useRef(null);
  const [file, setFile] = useState(null);
  const [answers, setAnswers] = useState([]);
  const [canSubmit, setCanSubmit] = useState(true);
  const [error, setError] = useState([]);
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth();

  function CustomToggle({ children, eventKey }) {
    const decoratedOnClick = useAccordionButton(eventKey);

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

    var question = questionForm.current.value;

    var body = {};
    var submit = false;
    if (question !== "" && file) {
      if (file.includes("base64,")) {
        body = {
          "question": question,
          "image": file.split(",")[1]
        }
      } else {
        body = {
          "question": question,
          "image": file
        }
      }
      submit = true;
    }

    if (submit && canSubmit) {
      setCanSubmit(false);
      setAnswers([...answers, { question: question, answer: null, sources: [] }]);
      fetch(url + "/projects/" + projectName + "/vision", {
        method: 'POST',
        headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + user.basicAuth }),
        body: JSON.stringify(body),
      })
        .then(response => response.json())
        .then((response) => {
          setAnswers([...answers, { question: question, answer: response.answer, sources: response.sources }]);
          questionForm.current.value = "";
          setCanSubmit(true);
        }).catch(err => {
          setError([...error, { "functionName": "onSubmitHandler", "error": err.toString() }]);
          setAnswers([...answers, { question: question, answer: "Error, something went wrong with my transistors.", sources: [] }]);
          setCanSubmit(true);
        });
    }
  }

  const convertToBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const fileReader = new FileReader();
      fileReader.readAsDataURL(file);
      fileReader.onload = () => {
        resolve(fileReader.result);
      };
      fileReader.onerror = (error) => {
        reject(error);
      };
    });
  };
  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    const base64 = await convertToBase64(file);
    urlForm.current.value = "";
    setFile(base64);
  };

  const handleSaveClick = () => {
    uploadForm.current.value = null;
    setFile(urlForm.current.value);
  };

  useEffect(() => {
    document.title = 'RestAI  Question ' + projectName;
  }, [projectName]);

  return (
    <>
      {error.length > 0 &&
        <Alert variant="danger">
          {JSON.stringify(error)}
        </Alert>
      }
      <Container style={{ marginTop: "20px" }}>
        <h1>Vision {projectName}</h1>
        <Form onSubmit={onSubmitHandler}>
          <Row>
            {answers.length > 0 &&
              <Col sm={12} style={{ marginTop: "20px" }}>
                <Card>
                  <Card.Header>Results</Card.Header>
                  <Card.Body>
                    {
                      answers.map((answer, index) => {
                        return (answer.answer != null ?
                          <div className='lineBreaks' key={index} style={index === 0 ? { marginTop: "0px" } : { marginTop: "10px" }}>
                            🧑<span className='highlight'>QUESTION:</span> {answer.question} <br />
                            🤖<span className='highlight'>ANSWER:</span> {answer.answer}
                            <Accordion>
                              <Row style={{ textAlign: "right", marginBottom: "0px" }}>
                                <CustomToggle eventKey="0">Details</CustomToggle>
                              </Row>
                              <Accordion.Collapse eventKey="0">
                                <Card.Body><ReactJson src={answer} enableClipboard={false} /></Card.Body>
                              </Accordion.Collapse>
                            </Accordion>
                            <hr />
                          </div>
                          :
                          <div className='lineBreaks' key={index} style={index === 0 ? { marginTop: "0px" } : { marginTop: "10px" }}>
                            🧑<span className='highlight'>QUESTION:</span> {answer.question} <br />
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
            <Col sm={8}>
              <InputGroup>
                <InputGroup.Text>{file ? "Question" : "Prompt"}</InputGroup.Text>
                <Form.Control ref={questionForm} rows="9" as="textarea" aria-label="Question textarea" />
              </InputGroup>
            </Col>
            <Col sm={4}>
              <center>
                <ModalImage
                  width="50%"
                  small={file ? file : NoImage}
                  large={file ? file : NoImage}
                  alt="Image preview"
                />
              </center>
            </Col>
          </Row>
          <hr/>
          <Row style={{ marginTop: "20px" }}>
            <Col sm={5}>
              <Form.Control ref={uploadForm} onChange={handleFileUpload} type="file" />
            </Col>
            <Col style={{ marginTop: "0.5%", paddingLeft: "3%" }} sm={1}>
              OR
            </Col>
            <Col sm={6}>
              <InputGroup className="mb-3">
                <Form.Control ref={urlForm}
                  placeholder="Enter url"
                  aria-label="Enter url"
                  aria-describedby="basic-addon2"
                />
                <Button onClick={handleSaveClick} variant="outline-secondary" id="button-addon2">
                  Save
                </Button>
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

export default Vision;