import { NavLink, Route, Routes } from "react-router-dom";
import OverviewPage from "./pages/OverviewPage";
import RegisterPage from "./pages/RegisterPage";
import LiveTestPage from "./pages/LiveTestPage";
import SessionsPage from "./pages/SessionsPage";
import SessionDetailPage from "./pages/SessionDetailPage";
import AdminPage from "./pages/AdminPage";
import { cn } from "./lib/utils";

const tabs = [
  { to: "/", label: "Overview", end: true },
  { to: "/register", label: "Register" },
  { to: "/live", label: "Live test" },
  { to: "/sessions", label: "Sessions" },
  { to: "/admin", label: "Admin" },
];

export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* The nav is a stamp row with a bottom mark — the same treatment Tabs now
          uses, so "tab" means one thing in this product instead of two. */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur-sm">
        <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-7 gap-y-1 px-6">
          <NavLink
            to="/"
            className="mr-3 py-3.5 font-display text-lg font-semibold tracking-tight text-foreground"
          >
            SentinelFace
          </NavLink>
          {tabs.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              className={({ isActive }) =>
                cn(
                  "stamp -mb-px border-b-2 py-3.5 font-medium transition-colors",
                  isActive
                    ? "border-b-instruct text-instruct"
                    : "border-b-transparent text-muted-foreground hover:text-foreground",
                )
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="mx-auto max-w-6xl px-6 pb-24 pt-10">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/live" element={<LiveTestPage />} />
          <Route path="/sessions" element={<SessionsPage />} />
          <Route path="/sessions/:id" element={<SessionDetailPage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </main>
    </div>
  );
}
