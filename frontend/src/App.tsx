import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { ScanFace } from "lucide-react";
import RegisterPage from "./pages/RegisterPage";
import SessionsPage from "./pages/SessionsPage";
import SessionDetailPage from "./pages/SessionDetailPage";
import AdminPage from "./pages/AdminPage";
import { cn } from "./lib/utils";

const tabs = [
  { to: "/register", label: "Register" },
  { to: "/sessions", label: "Sessions" },
  { to: "/admin", label: "Admin" },
];

export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b bg-card/85 backdrop-blur-md">
        <nav className="mx-auto flex max-w-6xl items-center gap-1 px-6 py-3.5">
          <span className="mr-6 flex items-center gap-2 font-semibold tracking-tight text-card-foreground">
            <ScanFace className="h-5 w-5 text-accent" />
            SentinelFace
          </span>
          {tabs.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-1.5 text-sm transition-colors",
                  isActive
                    ? "bg-accent-light font-medium text-accent"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-10">
        <Routes>
          <Route path="/" element={<Navigate to="/register" replace />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/sessions/:id" element={<SessionDetailPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </main>
    </div>
  );
}
