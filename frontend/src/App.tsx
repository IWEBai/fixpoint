import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import LandingPage from "./pages/LandingPage";
import Login from "./pages/Login";
import Analytics from "./pages/Analytics";
import RunHistory from "./pages/RunHistory";
import Installations from "./pages/Installations";
import Settings from "./pages/Settings";
import RepoSettings from "./pages/RepoSettings";
import OrgSettings from "./pages/OrgSettings";
import NotificationSettings from "./pages/NotificationSettings";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<Login />} />

        {/* Protected app routes */}
        <Route path="/app" element={<Layout />}>
          <Route index element={<Analytics />} />
          <Route path="runs" element={<RunHistory />} />
          <Route path="installations" element={<Installations />} />
          <Route path="settings" element={<Settings />} />
          <Route path="repo-settings" element={<RepoSettings />} />
          <Route path="org-settings" element={<OrgSettings />} />
          <Route path="notifications" element={<NotificationSettings />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
