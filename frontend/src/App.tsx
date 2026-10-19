import { NavLink, Route, Routes } from "react-router-dom";
import { NotesPage } from "./pages/NotesPage";
import { VoicePage } from "./pages/VoicePage";

export function App() {
  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="/">
          <Nib />
          <span className="wordmark">Qalam</span>
        </a>
        <p className="tagline">Speak it. See it handwritten. Print it.</p>
        <nav className="nav">
          <NavLink to="/" end>
            Notes
          </NavLink>
          <NavLink to="/voice">Voice</NavLink>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<NotesPage />} />
        <Route path="/voice" element={<VoicePage />} />
      </Routes>
    </div>
  );
}

function Nib() {
  return (
    <svg className="nib" viewBox="0 0 32 32" aria-hidden="true">
      <path d="M8 25c5-.4 9.2-6.4 16-16.2-6.2 2-9.6 5-13.6 11.2C8.6 22.6 8 24 8 25z" />
      <path d="M15.5 18.5c1.4 1.8 2 3.4 1.7 5" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}
