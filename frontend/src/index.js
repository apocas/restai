import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Route, Routes, Navigate } from "react-router-dom";
import './index.css';
import Home from './components/pages/Home/Home.js';
import Projects from './components/pages/Projects/Projects.js';
import Project from './components/pages/Projects/Project.js';
import Error from './components/pages/Error/Error.js';
import 'bootstrap/dist/css/bootstrap.css';

const root = ReactDOM.createRoot(document.getElementById('root'));

function Root() {
  return (
    <BrowserRouter basename="/">
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
          path={`/projects/:projectName/embbeddings`}
          element={<Projects />}
        />
        <Route
          path={`/projects/:projectName/question`}
          element={<Projects />}
        />
        <Route
          path={`/projects/:projectName/chat`}
          element={<Projects />}
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