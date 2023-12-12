import { Container, Table, Row, Alert } from 'react-bootstrap';
import React, { useState, useEffect, useRef, useContext } from "react";
import { AuthContext } from '../../common/AuthProvider.js';

function Models() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const [error, setError] = useState([]);
  const ref = useRef(null);
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth();

  const fetchInfo = () => {
    return fetch(url + "/info", { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => setInfo(d)
      ).catch(err => {
        setError([...error, { "functionName": "fetchInfo", "error": err.toString() }]);
      });
  }

  useEffect(() => {
    document.title = 'RestAI Project - Models info';
    fetchInfo();
  }, []);

  return (
    <>
      {error.length > 0 &&
        <Alert variant="danger">
          {JSON.stringify(error)}
        </Alert>
      }
      <Container style={{ marginTop: "20px" }}>
        <Row style={{ marginTop: "20px" }}>
          <h1>Inference Models</h1>
          <Table striped bordered hover responsive>
            <thead>
              <tr>
                <th>Name</th>
                <th>Privacy</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
            {
                info.llms.map((llm, index) => {
                  return (
                    <tr key={index}>
                      <td>{llm.name}</td>
                      <td>{llm.privacy}</td>
                      <td>{llm.description}</td>
                    </tr>
                  )
                })
              }
            </tbody>
          </Table>
        </Row>
        <Row style={{ marginTop: "20px" }}>
          <h1>Embeddings Models</h1>
          <Table striped bordered hover responsive>
            <thead>
              <tr>
                <th>Name</th>
                <th>Privacy</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
            {
                info.embeddings.map((embedding, index) => {
                  return (
                    <tr key={index}>
                      <td>{embedding.name}</td>
                      <td>{embedding.privacy}</td>
                      <td>{embedding.description}</td>
                    </tr>
                  )
                })
              }
            </tbody>
          </Table>
        </Row>
        <Row style={{ marginTop: "20px" }}>
          <h1>Document Loaders</h1>
          <Table striped bordered hover responsive>
            <thead>
              <tr>
                <th>Extension</th>
              </tr>
            </thead>
            <tbody>
            {
                info.loaders.map((loader, index) => {
                  return (
                    <tr key={index}>
                      <td>{loader}</td>
                    </tr>
                  )
                })
              }
            </tbody>
          </Table>
        </Row>
        <hr />
      </Container>
    </>
  );
}

export default Models;