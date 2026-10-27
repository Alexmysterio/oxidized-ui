import { lazy, Suspense, type ReactNode } from "react";
import { Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { ErrorBoundary } from "@/components/error-boundary";
import { AppShell } from "@/components/layout/app-shell";
import { ProtectedRoute, PublicOnlyRoute, RequireCapability, SetupRoute } from "@/components/layout/route-guards";
import { PageSkeleton } from "@/components/shared/loaders";
import { LoginPage } from "@/features/auth/login-page";
import { SetupPage } from "@/features/auth/setup-page";
import { ForbiddenPage, NotFoundPage } from "@/features/errors/error-pages";
import { useTheme } from "@/lib/theme";

const AuditPage = lazy(() => import("@/features/audit/audit-page").then((module) => ({ default: module.AuditPage })));
const BackupsPage = lazy(() => import("@/features/backups/backups-page").then((module) => ({ default: module.BackupsPage })));
const CompliancePage = lazy(() => import("@/features/compliance/compliance-page").then((module) => ({ default: module.CompliancePage })));
const MaintenancePage = lazy(() => import("@/features/maintenance/maintenance-page").then((module) => ({ default: module.MaintenancePage })));
const ConfigPage = lazy(() => import("@/features/config/config-page").then((module) => ({ default: module.ConfigPage })));
const DashboardPage = lazy(() => import("@/features/dashboard/dashboard-page").then((module) => ({ default: module.DashboardPage })));
const GroupsPage = lazy(() => import("@/features/groups/groups-page").then((module) => ({ default: module.GroupsPage })));
const StatusPage = lazy(() => import("@/features/logs/status-page").then((module) => ({ default: module.StatusPage })));
const NodeDetailPage = lazy(() => import("@/features/nodes/node-detail-page").then((module) => ({ default: module.NodeDetailPage })));
const NodesPage = lazy(() => import("@/features/nodes/nodes-page").then((module) => ({ default: module.NodesPage })));
const NodeTemplatesPage = lazy(() => import("@/features/templates/node-templates-page").then((module) => ({ default: module.NodeTemplatesPage })));
const ReconciliationPage = lazy(() => import("@/features/reconciliation/reconciliation-page").then((module) => ({ default: module.ReconciliationPage })));
const SitesPage = lazy(() => import("@/features/sites/sites-page").then((module) => ({ default: module.SitesPage })));
const ProfilePage = lazy(() => import("@/features/profile/profile-page").then((module) => ({ default: module.ProfilePage })));
const SystemPage = lazy(() => import("@/features/system/system-page").then((module) => ({ default: module.SystemPage })));
const UsersPage = lazy(() => import("@/features/users/users-page").then((module) => ({ default: module.UsersPage })));

function Page({ children }: { children: ReactNode }) {
  return <Suspense fallback={<PageSkeleton />}>{children}</Suspense>;
}

function AppToaster() {
  const { resolvedTheme } = useTheme();
  return (
    <Toaster
      theme={resolvedTheme}
      position="top-right"
      closeButton
      richColors
      toastOptions={{
        classNames: {
          toast: "!rounded-lg !border-border !bg-popover !text-popover-foreground !shadow-lift",
          description: "!text-muted-foreground",
        },
      }}
    />
  );
}

function RootLayout() {
  return (
    <>
      <ErrorBoundary>
        <Routes>
          <Route element={<PublicOnlyRoute />}>
            <Route path="/login" element={<LoginPage />} />
          </Route>
          <Route element={<SetupRoute />}>
            <Route path="/setup" element={<SetupPage />} />
          </Route>
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route index element={<Page><DashboardPage /></Page>} />
              <Route path="nodes" element={<Page><NodesPage /></Page>} />
              <Route path="nodes/:id" element={<Page><NodeDetailPage /></Page>} />
              <Route path="node-templates" element={<Page><NodeTemplatesPage /></Page>} />
              <Route path="reconciliation" element={<Page><ReconciliationPage /></Page>} />
              <Route path="sites" element={<Page><SitesPage /></Page>} />
              <Route
                path="groups"
                element={
                  <RequireCapability capability="groups.write">
                    <Page><GroupsPage /></Page>
                  </RequireCapability>
                }
              />
              <Route
                path="config"
                element={
                  <RequireCapability capability="config.read">
                    <Page><ConfigPage /></Page>
                  </RequireCapability>
                }
              />
              <Route
                path="status"
                element={
                  <RequireCapability capability="logs.read">
                    <Page><StatusPage /></Page>
                  </RequireCapability>
                }
              />
              <Route
                path="backups"
                element={
                  <RequireCapability capability="backups.trigger">
                    <Page><BackupsPage /></Page>
                  </RequireCapability>
                }
              />
              <Route
                path="maintenance"
                element={
                  <RequireCapability capability="backups.trigger">
                    <Page><MaintenancePage /></Page>
                  </RequireCapability>
                }
              />
              <Route
                path="compliance"
                element={
                  <RequireCapability capability="compliance.read">
                    <Page><CompliancePage /></Page>
                  </RequireCapability>
                }
              />
              <Route
                path="users"
                element={
                  <RequireCapability capability="users.manage">
                    <Page><UsersPage /></Page>
                  </RequireCapability>
                }
              />
              <Route
                path="audit"
                element={
                  <RequireCapability capability="audit.read">
                    <Page><AuditPage /></Page>
                  </RequireCapability>
                }
              />
              <Route
                path="system"
                element={
                  <RequireCapability capability="system.manage">
                    <Page><SystemPage /></Page>
                  </RequireCapability>
                }
              />
              <Route path="profile" element={<Page><ProfilePage /></Page>} />
              <Route path="forbidden" element={<ForbiddenPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </ErrorBoundary>
      <AppToaster />
    </>
  );
}

export function App() {
  return <RootLayout />;
}
