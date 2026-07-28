import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router";

import { App } from "./App";
import "./styles.css";

const rootEl = document.getElementById("root");
if (rootEl) {
  ReactDOM.createRoot(rootEl).render(
    <React.StrictMode>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </React.StrictMode>,
  );
}
