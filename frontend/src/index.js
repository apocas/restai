import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import Navigation from './components/common/Navigation.js'
import './assets/css/index.css';
import Projects from './components/pages/Projects/Projects.js';
import Models from './components/pages/Projects/Models.js';
import Project from './components/pages/Projects/Project.js';
import ProjectsEdit from './components/pages/Projects/Edit.js';
import Chat from './components/pages/Projects/Chat.js';
import Question from './components/pages/Projects/Question.js';
import Vision from './components/pages/Projects/Vision.js';
import Hardware from './components/pages/Hardware/Hardware.js';
import Users from './components/pages/Users/Users.js';
import User from './components/pages/Users/User.js';
import UsersEdit from './components/pages/Users/Edit.js';
import Login from './components/pages/Login/Login.js';
import Error from './components/pages/Error/Error.js';
import PrivateRoute from './components/common/PrivateRoute.js';
import AuthProvider from './components/common/AuthProvider.js';
import 'bootstrap/dist/css/bootstrap.css';
import { Container, Row, Col } from 'react-bootstrap';

const root = ReactDOM.createRoot(document.getElementById('root'));

function Root() {
  return (
    <>
      <BrowserRouter basename="/admin">
        <AuthProvider>
          <Navigation />
          <Routes>
            {/* Private Routes */}
            <Route path={'/'} element={<PrivateRoute />}>
              <Route path={`/`} element={<Projects />} />
              <Route path={`/projects`} element={<Projects />} />
              <Route path={`/models`} element={<Models />} />
              <Route path={`/projects/:projectName`} element={<Project />} />
              <Route path={`/projects/:projectName/edit`} element={<ProjectsEdit />} />
              <Route path={`/projects/:projectName/question`} element={<Question />} />
              <Route path={`/projects/:projectName/chat`} element={<Chat />} />
              <Route path={`/projects/:projectName/vision`} element={<Vision />} />
              <Route path={`/users`} element={<Users />} />
              <Route path={`/users/:username`} element={<User />} />
              <Route path={`/users/:username/edit`} element={<UsersEdit />} />
              <Route path={`/hardware`} element={<Hardware />} />
            </Route>
            {/* Public Routes */}
            <Route
              path={`/login`}
              element={<Login />}
            />
            <Route
              path={`/error`}
              element={<Error />}
            />
            <Route
              path={`*`}
              element={<Navigate to="/error" />}
            />
          </Routes>

          <Container style={{ marginTop: "20px", marginBottom: "20px", textAlign: "center" }}>
            <Row>
              <Col sm={12}>
                <hr />
                <a href="https://github.com/apocas/restai"><b>RestAI</b>, so many 'A's and 'I's, so little time...</a>
              </Col>
            </Row>
          </Container>
        </AuthProvider>
      </BrowserRouter>
    </>
  );
}

root.render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);