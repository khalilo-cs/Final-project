import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { AiBrainPage } from "./pages/AiBrainPage";
import { CoursePage, FacultyDashboard } from "./pages/FacultyDashboard";
import { LoginPage } from "./pages/LoginPage";
import { ProjectPage } from "./pages/ProjectPage";
import { StudentHome } from "./pages/StudentHome";
import { VivaPage, VivaReviewPage } from "./pages/VivaPage";

function AppRoutes() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <LoginPage />;
  const staff = user.role === "faculty" || user.role === "admin";
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={staff ? <FacultyDashboard /> : <StudentHome />} />
        <Route path="projects/:id" element={<ProjectPage />} />
        <Route path="viva/:id" element={<VivaPage />} />
        {staff && <Route path="viva/:id/review" element={<VivaReviewPage />} />}
        {staff && <Route path="courses/:id" element={<CoursePage />} />}
        {staff && <Route path="ai" element={<AiBrainPage />} />}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
