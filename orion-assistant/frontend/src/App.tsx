import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Sidebar } from "./components/Sidebar";
import { Topbar } from "./components/Topbar";
import { Dashboard } from "./pages/Dashboard";
import { Chat } from "./pages/Chat";
import { Placeholder } from "./pages/Placeholder";

export default function App() {
  return <BrowserRouter><div className="app-shell"><Sidebar/><main className="main"><Topbar/><Routes>
    <Route path="/" element={<Dashboard/>}/><Route path="/chat" element={<Chat/>}/>
    {[["/tasks","Tasks"],["/memory","Memory"],["/knowledge","Knowledge"],["/tools","Tools"],["/mcp","MCP"],["/automations","Automations"],["/connectors","Connectors"],["/evaluation","Evaluation"],["/security","Security"],["/settings","Settings"]].map(([path,title])=><Route key={path} path={path} element={<Placeholder title={title as string}/>}/>)}
  </Routes></main></div></BrowserRouter>;
}
