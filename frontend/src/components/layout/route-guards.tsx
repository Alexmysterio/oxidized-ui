import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { BootScreen } from "@/components/shared/loaders";
import { useAuth } from "@/lib/auth";
import { ForbiddenPage } from "@/features/errors/error-pages";

export function ProtectedRoute() {
  const { loading, setupRequired, user } = useAuth();
  const location = useLocation();
  if (loading) return <BootScreen />;
  if (setupRequired) return <Navigate to="/setup" replace />;
  if (!user) return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  return <Outlet />;
}

export function PublicOnlyRoute() {
  const { loading, setupRequired, user } = useAuth();
  if (loading) return <BootScreen />;
  if (setupRequired) return <Navigate to="/setup" replace />;
  if (user) return <Navigate to="/" replace />;
  return <Outlet />;
}

export function SetupRoute() {
  const { loading, setupRequired, user } = useAuth();
  if (loading) return <BootScreen />;
  if (!setupRequired) return <Navigate to={user ? "/" : "/login"} replace />;
  return <Outlet />;
}

export function RequireCapability({ capability, children }: { capability: string; children: ReactNode }) {
  const { can } = useAuth();
  if (!can(capability)) return <ForbiddenPage />;
  return <>{children}</>;
}
