/**
 * main.jsx - Application Entry Point
 *
 * Bootstraps the SmartHire React application by mounting the root <App />
 * component inside React.StrictMode for development-time warnings.
 */
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
