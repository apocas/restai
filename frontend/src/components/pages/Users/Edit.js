import { Container, Row, Form, Col, Button, Alert } from 'react-bootstrap';
import React, { useState, useEffect, useRef, useContext } from "react";
import { useParams } from "react-router-dom";
import { AuthContext } from '../../common/AuthProvider.js';

function Edit() {

  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [error, setError] = useState([]);
  const passwordForm = useRef(null)
  const isadminForm = useRef(null)
  var { username } = useParams();
  const { getBasicAuth } = useContext(AuthContext);
  const user = getBasicAuth();

  // TODO: response handling
  const onSubmitHandler = (event) => {
    event.preventDefault();
    var body = "";
    if (passwordForm.current.value === "" && user.admin) {
      body = JSON.stringify({
        "is_admin": isadminForm.current.checked
      })
    } else if (passwordForm.current.value !== "" && user.admin) {
      body = JSON.stringify({
        "password": passwordForm.current.value,
        "is_admin": isadminForm.current.checked
      })
    } else {
      body = JSON.stringify({
        "password": passwordForm.current.value
      })
    }

    fetch(url + "/users/" + username, {
      method: 'PATCH',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + user.basicAuth }),
      body: body,
    })
      .then(response => response.json())
      .catch(err => {
        setError([...error, { "functionName": "onSubmitHandler", "error": err.toString() }]);
      });

  }

  const fetchUser = (username) => {
    return fetch(url + "/users/" + username, { headers: new Headers({ 'Authorization': 'Basic ' + user.basicAuth }) })
      .then((res) => res.json())
      .then((d) => {
        isadminForm.current.checked = d.is_admin
      }
      ).catch(err => {
        setError([...error, { "functionName": "fetchUser", "error": err.toString() }]);
      });
  }

  useEffect(() => {
    document.title = 'RestAI Users';
    fetchUser(username);
  }, []);


  return (
    <>
      {error.length > 0 &&
        <Alert variant="danger">
          {JSON.stringify(error)}
        </Alert>
      }
      <Container style={{ marginTop: "20px" }}>
        <h1>Edit User {username}</h1>
        <Form onSubmit={onSubmitHandler}>
          <Row className="mb-3">
            <Form.Group as={Col} controlId="formGridUserName">
              <Form.Label>Password</Form.Label>
              <Form.Control ref={passwordForm} />
            </Form.Group>
            {user.admin &&
              <Form.Group as={Col} controlId="formGridAdmin">
                <Form.Check ref={isadminForm} type="checkbox" label="Admin" />
              </Form.Group>
            }
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