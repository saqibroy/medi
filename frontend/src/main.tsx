/** React entry point.
 *
 * Vite loads this file from index.html. React then renders App into #root and
 * Tailwind styles are imported once for the whole application.
 */

import React from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
