import { Route, Routes } from "react-router-dom";
import { TaskList } from "./pages/TaskList";
import { TaskDetail } from "./pages/TaskDetail";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<TaskList />} />
      <Route path="/tasks/:id" element={<TaskDetail />} />
    </Routes>
  );
}