import { Container, Row, Form, InputGroup, Col, Card, Button, Spinner, Alert, Accordion } from 'react-bootstrap';
import { useAccordionButton } from 'react-bootstrap/AccordionButton';
import { useParams } from "react-router-dom";
import React, { useState, useEffect, useRef, useContext } from "react";
import { AuthContext } from '../../common/AuthProvider.js';
import ReactJson from '@microlink/react-json-view';
import ModalImage from "react-modal-image";
import NoImage from '../../../assets/img/no-image.jpg'
import { FileUploader } from "react-drag-drop-files";

const fileTypes = ["JPG", "PNG", "GIF", "JPEGZ"];

function Vision() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  var { projectName } = useParams();
  const questionForm = useRef(null);
  const urlForm = useRef(null);
  const [uploadForm, setUploadForm] = useState(null);
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
    if (question !== "") {
      if (file && file.includes("base64,")) {
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
        .then(function (response) {
          if (!response.ok) {
            response.json().then(function (data) {
              setError([...error, { "functionName": "onSubmitHandler", "error": data.detail }]);
            });
            throw Error(response.statusText);
          } else {
            return response.json();
          }
        })
        .then((response) => {
          setAnswers([...answers, { question: question, answer: response.answer, sources: response.sources, image: response.image }]);
          questionForm.current.value = "";
          setCanSubmit(true);
        }).catch(err => {
          setError([...error, { "functionName": "onSubmitHandler", "error": err.toString() }]);
          setAnswers([...answers, { question: question, answer: "Error, something went wrong with my transistors.", sources: [], image: null }]);
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
  const handleFileUpload = async (file) => {
    //const file = e.target.files[0];
    const base64 = await convertToBase64(file);
    urlForm.current.value = "";
    setFile(base64);
  };

  const handleSaveClick = () => {
    if (isValidUrl(urlForm.current.value)) {
      setUploadForm(null);
      setFile(urlForm.current.value);
    } else {
      alert("Url provided is not a valid one!");
    }
  };

  const isValidUrl = urlString => {
    var urlPattern = new RegExp('^(https?:\\/\\/)?' + // validate protocol
      '((([a-z\\d]([a-z\\d-]*[a-z\\d])*)\\.)+[a-z]{2,}|' + // validate domain name
      '((\\d{1,3}\\.){3}\\d{1,3}))' + // validate OR ip (v4) address
      '(\\:\\d+)?(\\/[-a-z\\d%_.~+]*)*' + // validate port and path
      '(\\?[;&a-z\\d%_.~+=-]*)?' + // validate query string
      '(\\#[-a-z\\d_]*)?$', 'i'); // validate fragment locator
    return !!urlPattern.test(urlString);
  }

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
                            {answer.image &&
                              <Col sm={4}>
                                <ModalImage
                                  small={`data:image/jpg;base64,${answer.image}`}
                                  large={`data:image/jpg;base64,${answer.image}`}
                                  alt="Image preview"
                                />
                              </Col>
                            }
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
              <InputGroup style={{ height: "100%" }}>
                <InputGroup.Text>{file ? "Question" : "Prompt"}</InputGroup.Text>
                <Form.Control ref={questionForm} rows="5" as="textarea" aria-label="Question textarea" />
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
          <hr />
          <Row style={{ marginTop: "20px" }}>
            <Col sm={5}>
              <FileUploader fileOrFiles={uploadForm} classes="dragging" handleChange={handleFileUpload} name="file" types={fileTypes} />
            </Col>
            <Col style={{ marginTop: "0.9%", paddingLeft: "2.5%" }} sm={1}>
              OR
            </Col>
            <Col sm={6}>
              <InputGroup style={{ height: "90%" }} className="mb-3">
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