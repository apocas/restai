import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import './assets/css/index.css';
import Projects from './components/pages/Projects/Projects.js';
import Project from './components/pages/Projects/Project.js';
import Chat from './components/pages/Projects/Chat.js';
import Question from './components/pages/Projects/Question.js';
import Error from './components/pages/Error/Error.js';
import 'bootstrap/dist/css/bootstrap.css';

const root = ReactDOM.createRoot(document.getElementById('root'));

function Root() {
  return (
    <BrowserRouter basename="/admin">
      <Routes>
        <Route exact path="/" element={<Projects />} />
        <Route exact
          path={`/projects`}
          element={<Projects />}
        />
        <Route
          path={`/projects/:projectName`}
          element={<Project />}
        />
        <Route
          path={`/projects/:projectName/question`}
          element={<Question />}
        />
        <Route
          path={`/projects/:projectName/chat`}
          element={<Chat />}
        />
        <Route
          path={`/error`}
          element={<Error />}
        />
        <Route path="*" element={<Navigate to="/error" />} />
      </Routes>
    </BrowserRouter>
  );
}

root.render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);