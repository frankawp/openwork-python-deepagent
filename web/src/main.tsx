import React from "react"
import ReactDOM from "react-dom/client"
import App from "./App"
import "@ant-design/x-markdown/dist/x-markdown.css"
import "@ant-design/x-markdown/themes/light.css"
import "./index.css"
import { attachWindowApi } from "./lib/window-api"

attachWindowApi()

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
