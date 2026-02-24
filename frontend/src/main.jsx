/**
 * Frontend Application Entry Point
 * ================================
 *
 * This is the main entry point for the SmartHire React application.
 * Sets up React, mounts the app to the DOM, and enables Strict Mode for development.
 *
 * Imports:
 *   - React & ReactDOM: Core rendering libraries
 *   - App: Root React component containing all UI
 *   - index.css: Global styles (TailwindCSS)
 */

// Import React library for component structure
import React from 'react';

// Import ReactDOM for rendering React components to the DOM
import ReactDOM from 'react-dom/client';

// Import the main App component containing all application logic
import App from './App';

// Import global CSS styles
// Includes TailwindCSS configuration and application-wide styles
import './index.css';

/**
 * Create React Root and Render Application
 *
 * 1. Find the DOM element with id="root" (from public/index.html)
 * 2. Create React root for mounting the application
 * 3. Wrap App in React.StrictMode for development checks
 * 4. Render the mounted application in the browser
 */

// Find the DOM element where React will mount the application
// This element must exist in public/index.html: <div id="root"></div>
const rootElement = document.getElementById('root');

// Create React 18 root (new API, replacing ReactDOM.render())
// Root is the entry point for rendering the React component tree
const root = ReactDOM.createRoot(rootElement);

// Render the application with StrictMode enabled
// StrictMode: Development tool that highlights potential issues
// - Double-invokes components to detect state mutations
// - Checks for deprecated API usage
// - Validates component lifecycle patterns
// Only active in development; has zero effect in production
root.render(
  <React.StrictMode>
    {/* Main App component: contains all routes, state, and UI */}
    <App />
  </React.StrictMode>,
);
