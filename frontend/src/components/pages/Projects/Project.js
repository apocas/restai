import CustomNavBar from '../../common/navBar.js'
import Container from 'react-bootstrap/Container';
import Table from 'react-bootstrap/Table';
import Row from 'react-bootstrap/Row';
import Form from 'react-bootstrap/Form';
import Col from 'react-bootstrap/Col';
import Button from 'react-bootstrap/Button';
import ListGroup from 'react-bootstrap/ListGroup';
import { useParams } from "react-router-dom";


import React, { useState, useEffect } from "react";

function Project() {

  const url = "https://ai.ptisp.systems";
  const [data, setData] = useState({ projects: [] });
  const [files, setFiles] = useState({ files: [] });
  const [file, setFile] = useState(null);
  var { projectName } = useParams();


  // TODO: error handling
  const fetchProject = (projectName) => {
    return fetch(url + "/projects/" + projectName)
      .then((res) => res.json())
      .then((d) => setData(d))
  }
  // TODO: error handling
  const fetchFiles = (projectName) => {
    return fetch(url + "/projects/" + projectName + "/embeddings/files")
      .then((res) => res.json())
      .then((d) => setFiles(d))
  }

  // TODO: error handling
  const handleDeleteClick = (fileName) => {
    alert(fileName);
    fetch(url + "/projects/" + projectName + "/embeddings/files/" + fileName, { method: 'DELETE' })
      .then(() => {
        fetchProject(projectName);
        fetchFiles(projectName);
      });
  }


  const handleFileChange = (e) => {
    if (e.target.files) {
      setFile(e.target.files[0]);
    }
  };

  // TODO: error handling and response
  const onSubmitHandler = (event) => {
    event.preventDefault();
    if (file) {
      const formData = new FormData();
      formData.append("file", file);

      fetch(url + "/projects/" + projectName + "/embeddings/ingest/upload", {
        method: 'POST',
        body: formData,
      })
        .then(response => response.json())
        .then(() => fetchFiles(projectName))
    }
  }

  useEffect(() => {
    document.title = 'RestAI Project ' + projectName;
    fetchProject(projectName);
    fetchFiles(projectName);
  }, [projectName]);

  return (
    <>
      <CustomNavBar />
      <Container style={{ marginTop: "20px" }}>
        <Row style={{ marginTop: "20px" }}>
          <h1>Status</h1>
          <ListGroup>
            <ListGroup.Item>Project: {data.project}</ListGroup.Item>
            <ListGroup.Item>LLM: {data.llm}</ListGroup.Item>
            <ListGroup.Item>Embeddings: {data.embeddings}</ListGroup.Item>
            <ListGroup.Item>Documents: {data.documents}</ListGroup.Item>
            <ListGroup.Item>Metadatas: {data.metadatas}</ListGroup.Item>
          </ListGroup>
        </Row>
        <Row style={{ marginTop: "20px" }}>
          <h1>Files</h1>
          <Table striped bordered hover>
            <thead>
              <tr>
                <th>#</th>
                <th>Files</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {
                files.files.map((file, index) => {
                  return (
                    <tr key={index}>
                      <td>{index}</td>
                      <td>
                        {file}
                      </td>
                      <td>
                        <button onClick={() => handleDeleteClick(file)}>Delete</button>
                      </td>
                    </tr>
                  )
                })
              }
            </tbody>
          </Table>
        </Row>
        <Row style={{ marginTop: "20px" }}>
          <h1>Upload File</h1>
          <Form onSubmit={onSubmitHandler}>
            <Form.Group as={Row} className="mb-3" controlId="formHorizontalEmail">
              <Form.Label column sm={2}>
                File
              </Form.Label>
              <Col sm={8}>
                <Form.Control onChange={handleFileChange} type="file" />
              </Col>
              <Col sm={2}>
                <Button type="submit">Upload</Button>
              </Col>
            </Form.Group>
          </Form>
          {file && (
            <section>
              File details:
              <ul>
                <li>Name: {file.name}</li>
                <li>Type: {file.type}</li>
                <li>Size: {file.size} bytes</li>
              </ul>
            </section>
          )}
        </Row>
      </Container>
    </>
  );
}

export default Project;