import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Base styles first: view stylesheets override them, and Vite emits CSS in import order.
import "./styles.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);

