import type {
  ApiErrorPayload,
  ApiFieldError,
  ApiToken,
  AuditEntry,
  BackupSchedule,
  BackupScheduleList,
  Catalog,
  ComplianceNodeReport,
  ComplianceReport,
  ConfigTemplate,
  ConfigDraftResponse,
  ConfigRevisionDetail,
  ConfigSearchResult,
  ConfigState,
  ConfigValidation,
  DiffResult,
  ExportStatus,
  ExportVerification,
  Group,
  GroupInput,
  GroupList,
  HealthHistory,
  HealthSnapshot,
  ImportSummary,
  Job,
  JobPriorityRule,
  LogSnapshot,
  MaintenanceWindow,
  Meta,
  MfaChallenge,
  MfaEnableResult,
  MfaSetup,
  MfaStatus,
  Node,
  NodeCompare,
  NodeConnectionTest,
  NodeDiff,
  NodeFacts,
  NodeHistory,
  NodeInput,
  NodeListParams,
  NodePingResult,
  NodeStatusDetail,
  NodeTagCount,
  NodeTemplate,
  NotificationChannel,
  NotificationEvent,
  NotificationKind,
  Paginated,
  ReconciliationReport,
  ReportList,
  Revision,
  Role,
  SavedFilter,
  ScheduledApply,
  SearchResults,
  SessionInfo,
  SessionPayload,
  SitesResponse,
  StatusPayload,
  SystemSettings,
  User,
  UserPreferences,
  VersionContent,
  VersionsResponse,
} from "@/types/api";

let csrfToken: string | null = null;
const unauthorizedEvent = "oxidized:unauthorized";

export class ApiError extends Error {
  status: number;
  code: string;
  params: Record<string, unknown>;
  fields: ApiFieldError[];
  requestId?: string;

  constructor(
    status: number,
    code: string,
    params: Record<string, unknown> = {},
    fields: ApiFieldError[] = [],
    requestId?: string,
  ) {
    super(code);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.params = params;
    this.fields = fields;
    this.requestId = requestId;
  }
}

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export function getCsrfToken(): string | null {
  return csrfToken;
}

type QueryValue = string | number | boolean | null | undefined;
type Query = Record<string, QueryValue | QueryValue[]>;

function buildQuery(query?: Query): string {
  if (!query) return "";
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    if (Array.isArray(value)) {
      value.forEach((entry) => {
        if (entry !== undefined && entry !== null && entry !== "") params.append(key, String(entry));
      });
    } else {
      params.set(key, String(value));
    }
  });
  const text = params.toString();
  return text ? `?${text}` : "";
}

interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Query;
  formData?: FormData;
  skipUnauthorizedEvent?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers = new Headers({ Accept: "application/json" });
  if (method !== "GET" && csrfToken) headers.set("X-CSRF-Token", csrfToken);
  let body: BodyInit | undefined;
  if (options.formData) {
    body = options.formData;
  } else if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }
  const response = await fetch(`/api${path}${buildQuery(options.query)}`, {
    method,
    credentials: "include",
    headers,
    body,
    cache: "no-store",
  });
  if (response.status === 401 && !options.skipUnauthorizedEvent) {
    window.dispatchEvent(new Event(unauthorizedEvent));
  }
  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = null;
    }
    const error = payload?.error;
    throw new ApiError(
      response.status,
      error?.code ?? "app.internal_error",
      error?.params ?? {},
      error?.fields ?? [],
      error?.request_id,
    );
  }
  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    return (await response.text()) as T;
  }
  const payload = (await response.json()) as T & { csrf_token?: string };
  if (typeof payload?.csrf_token === "string") setCsrfToken(payload.csrf_token);
  return payload as T;
}

async function requestText(path: string, query?: Query): Promise<string> {
  const response = await fetch(`/api${path}${buildQuery(query)}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (response.status === 401) window.dispatchEvent(new Event(unauthorizedEvent));
  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = null;
    }
    throw new ApiError(
      response.status,
      payload?.error?.code ?? "app.internal_error",
      payload?.error?.params ?? {},
      payload?.error?.fields ?? [],
      payload?.error?.request_id,
    );
  }
  return response.text();
}

function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header)?.[1];
  if (encoded) return decodeURIComponent(encoded);
  const plain = /filename="?([^";]+)"?/i.exec(header)?.[1];
  return plain || fallback;
}

async function download(path: string, query: Query | undefined, fallbackName: string): Promise<void> {
  const response = await fetch(`/api${path}${buildQuery(query)}`, {
    credentials: "include",
    cache: "no-store",
  });
  if (response.status === 401) window.dispatchEvent(new Event(unauthorizedEvent));
  if (!response.ok) {
    throw new ApiError(response.status, "node.export_failed");
  }
  const blob = await response.blob();
  const filename = filenameFromDisposition(response.headers.get("content-disposition"), fallbackName);
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}


async function downloadEncryptedExport(passphrase: string): Promise<void> {
  const headers = new Headers({ Accept: "application/octet-stream", "Content-Type": "application/json" });
  if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  const response = await fetch("/api/system/export", {
    method: "POST",
    credentials: "include",
    headers,
    body: JSON.stringify({ passphrase }),
    cache: "no-store",
  });
  if (response.status === 401) window.dispatchEvent(new Event(unauthorizedEvent));
  if (!response.ok) {
    let payload: ApiErrorPayload | null = null;
    try {
      payload = (await response.json()) as ApiErrorPayload;
    } catch {
      payload = null;
    }
    throw new ApiError(
      response.status,
      payload?.error?.code ?? "app.internal_error",
      payload?.error?.params ?? {},
      payload?.error?.fields ?? [],
      payload?.error?.request_id,
    );
  }
  const blob = await response.blob();
  const filename = filenameFromDisposition(response.headers.get("content-disposition"), "oxidized-ui.oxui");
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(href);
}

export const api = {
  unauthorizedEvent,
  meta: () => request<Meta>("/meta", { skipUnauthorizedEvent: true }),
  health: () => request<Record<string, unknown>>("/health", { skipUnauthorizedEvent: true }),

  session: () => request<SessionPayload>("/auth/session", { skipUnauthorizedEvent: true }),
  sessions: () => request<{ sessions: SessionInfo[] }>("/auth/sessions"),
  apiTokens: () => request<{ items: ApiToken[] }>("/auth/tokens"),
  createApiToken: (name: string, role: string, days: number) =>
    request<{ token: string; item: ApiToken }>("/auth/tokens", { method: "POST", body: { name, role, days } }),
  revokeApiToken: (id: number) => request<void>(`/auth/tokens/${id}`, { method: "DELETE" }),
  revokeSession: (id: number) => request<void>(`/auth/sessions/${id}`, { method: "DELETE" }),
  login: (username: string, password: string) =>
    request<SessionPayload | MfaChallenge>("/auth/login", {
      method: "POST",
      body: { username, password },
      skipUnauthorizedEvent: true,
    }),
  loginMfa: (challenge_token: string, code: string) =>
    request<SessionPayload>("/auth/login/mfa", {
      method: "POST",
      body: { challenge_token, code },
      skipUnauthorizedEvent: true,
    }),
  mfaStatus: () => request<MfaStatus>("/auth/mfa"),
  mfaSetup: () => request<MfaSetup>("/auth/mfa/setup", { method: "POST" }),
  mfaEnable: (code: string) =>
    request<MfaEnableResult>("/auth/mfa/enable", { method: "POST", body: { code } }),
  mfaDisable: (password: string, code: string) =>
    request<void>("/auth/mfa/disable", { method: "POST", body: { password, code } }),
  setup: (payload: { username: string; password: string; language: string; theme?: string }) =>
    request<SessionPayload>("/setup", {
      method: "POST",
      body: payload,
      skipUnauthorizedEvent: true,
    }),
  logout: () => request<void>("/auth/logout", { method: "POST", skipUnauthorizedEvent: true }),
  updateMe: (payload: { language?: string; theme?: string; full_name?: string | null; email?: string | null }) =>
    request<{ user: User; capabilities: string[] }>("/me", { method: "PATCH", body: payload }),
  uploadAvatar: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<{ user: User }>("/me/avatar", { method: "POST", formData });
  },
  deleteAvatar: () => request<void>("/me/avatar", { method: "DELETE" }),
  changePassword: (current_password: string, new_password: string) =>
    request<SessionPayload>("/me/password", {
      method: "POST",
      body: { current_password, new_password },
    }),

  users: (query?: { search?: string; role?: string; is_active?: boolean; page?: number; page_size?: number }) =>
    request<Paginated<User>>("/users", { query }),
  user: (id: number) => request<User>(`/users/${id}`),
  createUser: (payload: { username: string; password: string; role: Role; language: string; full_name?: string | null; email?: string | null }) =>
    request<User>("/users", { method: "POST", body: payload }),
  updateUser: (id: number, payload: { role?: Role; is_active?: boolean; language?: string; full_name?: string | null; email?: string | null }) =>
    request<User>(`/users/${id}`, { method: "PATCH", body: payload }),
  resetUserPassword: (id: number, new_password: string) =>
    request<void>(`/users/${id}/password`, { method: "POST", body: { new_password } }),
  deleteUser: (id: number) => request<void>(`/users/${id}`, { method: "DELETE" }),

  nodes: (query?: NodeListParams) => request<Paginated<Node>>("/nodes", { query: query as Query }),
  node: (id: number) => request<Node>(`/nodes/${id}`),
  nodeTags: () => request<{ items: NodeTagCount[] }>("/nodes/tags"),
  sites: (tag = "Site") => request<SitesResponse>("/nodes/sites", { query: { tag } }),
  collectFacts: (ids: number[]) => request<Job>("/nodes/facts/collect", { method: "POST", body: { ids } }),
  collectNodeFacts: (id: number) => request<NodeFacts>(`/nodes/${id}/facts/collect`, { method: "POST" }),
  createNode: (payload: NodeInput) => request<{ node: Node; reload_status: string; warnings: string[] }>("/nodes", { method: "POST", body: payload }),
  updateNode: (id: number, payload: Partial<NodeInput>) =>
    request<{ node: Node; reload_status: string; warnings: string[] }>(`/nodes/${id}`, { method: "PATCH", body: payload }),
  deleteNode: (id: number) => request<{ deleted: number; reload_status: string; warnings: string[] }>(`/nodes/${id}`, { method: "DELETE" }),
  bulkNodes: (payload: {
    action: "backup" | "change_group" | "delete" | "update" | "trust_host_key" | "set_tags";
    ids: number[];
    group_name?: string | null;
    model?: string | null;
    input?: string | null;
    port?: number | null;
    vars?: Record<string, unknown> | null;
    tags?: Record<string, string> | null;
    tags_mode?: "merge" | "replace";
  }) =>
    request<{ job_id?: number; updated?: number; deleted?: number; requested?: number; trusted?: number; failed?: unknown[]; reload_status?: string; warnings?: string[] }>("/nodes/bulk", { method: "POST", body: payload }),
  importNodes: (formData: FormData) => request<ImportSummary>("/nodes/import", { method: "POST", formData }),
  exportNodes: () => download("/nodes/export.csv", undefined, "oxidized-nodes.csv"),
  backupNode: (id: number) => request<Job>(`/nodes/${id}/backup`, { method: "POST" }),
  testNodeConnection: (id: number) => request<NodeConnectionTest>(`/nodes/${id}/test-connection`, { method: "POST" }),
  pingNode: (id: number) => request<NodePingResult>(`/nodes/${id}/ping`, { method: "POST" }),
  trustHostKey: (id: number) =>
    request<{ address: string; port: number; fingerprints: string[]; key_types: string[] }>(
      `/nodes/${id}/trust-host-key`,
      { method: "POST" },
    ),
  nodeHistory: (id: number) => request<NodeHistory>(`/nodes/${id}/history`),
  compareNodes: (left_id: number, right_id: number) => request<NodeCompare>("/nodes/compare", { query: { left_id, right_id } }),
  nodeStatus: (id: number, refresh = false) => request<NodeStatusDetail>(`/nodes/${id}/status`, { query: { refresh } }),
  nodeConfig: (id: number) => requestText(`/nodes/${id}/config`),
  nodeVersions: (id: number) => request<VersionsResponse>(`/nodes/${id}/versions`),
  nodeVersion: (id: number, oid: string) => request<VersionContent>(`/nodes/${id}/versions/${encodeURIComponent(oid)}`),
  nodeDiff: (id: number, from_oid: string, to_oid: string) =>
    request<NodeDiff>(`/nodes/${id}/diff`, { query: { from_oid, to_oid } }),
  downloadNode: (id: number, oid?: string) =>
    download(`/nodes/${id}/download`, { oid }, `${id}-${oid ?? "current"}.txt`),

  groups: () => request<GroupList>("/groups"),
  group: (name: string) => request<Group>(`/groups/${encodeURIComponent(name)}`),
  createGroup: (payload: GroupInput) => request<{ revision_id: number; requires_admin_apply: boolean; group: Group }>("/groups", { method: "POST", body: payload }),
  updateGroup: (name: string, payload: GroupInput, expectedRevisionId?: number | null) =>
    request<{ revision_id: number; requires_admin_apply: boolean; group: Group }>(`/groups/${encodeURIComponent(name)}`, {
      method: "PATCH",
      body: payload,
      query: { expected_revision_id: expectedRevisionId },
    }),
  deleteGroup: (name: string, expectedRevisionId?: number | null) =>
    request<void>(`/groups/${encodeURIComponent(name)}`, {
      method: "DELETE",
      query: { expected_revision_id: expectedRevisionId },
    }),

  config: () => request<ConfigState>("/config"),
  configCatalog: () => request<Catalog>("/config/catalog"),
  validateConfig: (payload: { config?: Record<string, unknown>; yaml?: string }) =>
    request<ConfigValidation>("/config/validate", { method: "POST", body: payload }),
  saveConfigDraft: (payload: { config?: Record<string, unknown>; yaml?: string; expected_revision_id?: number | null; origin?: "form" | "yaml"; note?: string }) =>
    request<ConfigDraftResponse>("/config/draft", { method: "POST", body: payload }),
  configRevisions: (page = 1, pageSize = 25) =>
    request<Paginated<Revision>>("/config/revisions", { query: { page, page_size: pageSize } }),
  configRevision: (id: number) => request<ConfigRevisionDetail>(`/config/revisions/${id}`),
  configRevisionDiff: (id: number, against?: number | null) =>
    request<DiffResult & { from: number | null; to: number }>(`/config/revisions/${id}/diff`, { query: { against } }),
  restoreConfigRevision: (id: number, note?: string) =>
    request<ConfigDraftResponse>(`/config/revisions/${id}/restore`, { method: "POST", body: { note } }),
  applyConfig: (revisionId: number) => request<Job>("/config/apply", { method: "POST", body: { revision_id: revisionId, restart: true } }),
  configSchedules: () => request<{ items: ScheduledApply[] }>("/config/schedule"),
  scheduleConfig: (revisionId: number, runAt: string) =>
    request<ScheduledApply>("/config/schedule", {
      method: "POST",
      body: { revision_id: revisionId, run_at: runAt },
    }),
  cancelConfigSchedule: (id: number) => request<void>(`/config/schedule/${id}`, { method: "DELETE" }),

  status: () => request<StatusPayload>("/status"),
  jobs: (query?: { status?: string; kind?: string; page?: number; page_size?: number }) =>
    request<Paginated<Job>>("/jobs", { query }),
  job: (id: number) => request<Job>(`/jobs/${id}`),
  cancelJob: (id: number) => request<void>(`/jobs/${id}`, { method: "DELETE" }),
  backupsAll: (ids?: number[]) => request<Job>("/backups/all", { method: "POST", body: ids ? { ids } : undefined }),
  backupSchedules: () => request<BackupScheduleList>("/backups/schedules"),
  createBackupSchedule: (group_name: string | null, interval_minutes: number) =>
    request<BackupSchedule>("/backups/schedules", { method: "POST", body: { group_name, interval_minutes } }),
  updateBackupSchedule: (id: number, payload: { interval_minutes?: number; enabled?: boolean }) =>
    request<BackupSchedule>(`/backups/schedules/${id}`, { method: "PATCH", body: payload }),
  deleteBackupSchedule: (id: number) => request<void>(`/backups/schedules/${id}`, { method: "DELETE" }),
  priorityRules: () => request<{ items: JobPriorityRule[] }>("/backups/priority-rules"),
  createPriorityRule: (payload: {
    scope_type: "group" | "tag";
    scope_key: string;
    scope_value?: string | null;
    priority: number;
  }) => request<JobPriorityRule>("/backups/priority-rules", { method: "POST", body: payload }),
  deletePriorityRule: (id: number) => request<void>(`/backups/priority-rules/${id}`, { method: "DELETE" }),

  nodeTemplates: () => request<{ items: NodeTemplate[] }>("/node-templates"),
  createNodeTemplate: (payload: Omit<NodeTemplate, "id" | "created_at" | "updated_at">) =>
    request<NodeTemplate>("/node-templates", { method: "POST", body: payload }),
  updateNodeTemplate: (id: number, payload: Partial<NodeTemplate>) =>
    request<NodeTemplate>(`/node-templates/${id}`, { method: "PATCH", body: payload }),
  deleteNodeTemplate: (id: number) => request<void>(`/node-templates/${id}`, { method: "DELETE" }),
  applyNodeTemplate: (id: number, payload: { name: string; address?: string | null; tags?: Record<string, string> }) =>
    request<{ node: Node; reload_status: string; warnings: string[] }>(`/node-templates/${id}/apply`, {
      method: "POST",
      body: payload,
    }),

  reconciliation: () => request<ReconciliationReport>("/reconciliation"),
  importReconciled: (names: string[]) =>
    request<{ imported: { id: number; name: string }[]; errors: { name: string; code: string }[] }>(
      "/reconciliation/import",
      { method: "POST", body: { names } },
    ),

  systemHealth: () => request<HealthSnapshot>("/system/health"),
  healthHistory: (hours = 168) => request<HealthHistory>("/system/health/history", { query: { hours } }),
  reports: () => request<ReportList>("/system/reports"),
  runReport: () => request<Job>("/system/reports/run", { method: "POST" }),
  testEmail: () => request<{ ok: boolean; reason?: string }>("/system/email/test", { method: "POST" }),
  downloadReport: (filename: string) => download(`/system/reports/${encodeURIComponent(filename)}`, undefined, filename),
  verifyExport: (passphrase?: string) =>
    request<ExportVerification>("/system/export/verify", { method: "POST", body: { passphrase: passphrase ?? null } }),

  maintenanceWindows: (include_finished = false) =>
    request<{ items: MaintenanceWindow[] }>("/maintenance", { query: { include_finished } }),
  createMaintenanceWindow: (payload: {
    scope_type: "node" | "group" | "global";
    node_id?: number | null;
    group_name?: string | null;
    starts_at: string;
    ends_at: string;
    reason?: string | null;
  }) => request<{ id: number }>("/maintenance", { method: "POST", body: payload }),
  deleteMaintenanceWindow: (id: number) => request<void>(`/maintenance/${id}`, { method: "DELETE" }),

  complianceTemplates: () => request<{ items: ConfigTemplate[] }>("/compliance/templates"),
  createComplianceTemplate: (payload: {
    name: string;
    scope_type: "global" | "group" | "model";
    scope_value?: string | null;
    content: string;
  }) => request<ConfigTemplate>("/compliance/templates", { method: "POST", body: payload }),
  updateComplianceTemplate: (
    id: number,
    payload: { name?: string; scope_type?: "global" | "group" | "model"; scope_value?: string | null; content?: string },
  ) => request<ConfigTemplate>(`/compliance/templates/${id}`, { method: "PATCH", body: payload }),
  deleteComplianceTemplate: (id: number) => request<void>(`/compliance/templates/${id}`, { method: "DELETE" }),
  complianceReport: (query?: { group?: string; model?: string; template_id?: number; limit?: number }) =>
    request<ComplianceReport>("/compliance/report", { query: query as Query }),
  complianceNodeReport: (nodeId: number, templateId?: number) =>
    request<ComplianceNodeReport>(`/compliance/report/${nodeId}`, {
      query: templateId ? { template_id: templateId } : undefined,
    }),

  preferences: () => request<UserPreferences>("/me/preferences"),
  updatePreferences: (payload: { favorites?: number[]; saved_filters?: SavedFilter[] }) =>
    request<UserPreferences>("/me/preferences", { method: "PATCH", body: payload }),

  exportStatus: () => request<ExportStatus>("/system/export"),
  configureExport: (payload: {
    kind: "sftp" | "s3";
    interval_hours: number;
    enabled: boolean;
    config: Record<string, unknown>;
  }) => request<ExportStatus>("/system/export", { method: "PUT", body: payload }),
  runExport: () => request<Job>("/system/export/run", { method: "POST" }),
  reloadOxidized: () => request<{ reloaded: boolean }>("/oxidized/reload", { method: "POST" }),
  restartOxidized: () => request<Job>("/oxidized/restart", { method: "POST" }),

  logs: (query?: { tail?: number; since?: string; level?: string; q?: string }) =>
    request<LogSnapshot>("/logs", { query }),
  downloadLogs: (query?: { since?: string; until?: string; level?: string; q?: string }) =>
    download("/logs/download", query, "oxidized-logs.txt"),

  audit: (query?: { actor?: string; action?: string; target_type?: string; target_id?: string; from?: string; to?: string; page?: number; page_size?: number }) =>
    request<Paginated<AuditEntry>>("/audit", { query }),
  exportAudit: () => download("/audit/export.csv", undefined, "oxidized-audit.csv"),
  exportEncrypted: (passphrase: string) => downloadEncryptedExport(passphrase),

  systemSettings: () => request<SystemSettings>("/system/settings"),
  updateSystemSettings: (payload: Partial<SystemSettings>) =>
    request<SystemSettings>("/system/settings", { method: "PATCH", body: payload }),
  testNotification: () => request<{ ok: boolean; results?: { id: number; name: string; ok: boolean }[] }>("/system/notify-test", { method: "POST" }),
  notifications: () => request<{ items: NotificationChannel[] }>("/system/notifications"),
  createNotification: (payload: { name: string; kind: NotificationKind; enabled: boolean; events: NotificationEvent[]; config: Record<string, string> }) =>
    request<NotificationChannel>("/system/notifications", { method: "POST", body: payload }),
  updateNotification: (id: number, payload: Partial<{ name: string; kind: NotificationKind; enabled: boolean; events: NotificationEvent[]; config: Record<string, string> }>) =>
    request<NotificationChannel>(`/system/notifications/${id}`, { method: "PATCH", body: payload }),
  deleteNotification: (id: number) => request<void>(`/system/notifications/${id}`, { method: "DELETE" }),
  testNotificationChannel: (id: number) => request<{ ok: boolean; results: { id: number; name: string; ok: boolean }[] }>(`/system/notifications/${id}/test`, { method: "POST" }),
  uploadLogo: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<SystemSettings>("/system/branding/logo", { method: "POST", formData });
  },
  deleteLogo: () => request<void>("/system/branding/logo", { method: "DELETE" }),
  testConnection: (target: "oxidized" | "docker") =>
    request<{ ok: boolean; target: string }>("/system/test", { method: "POST", body: { target } }),

  search: (q: string) => request<SearchResults>("/search", { query: { q } }),
  searchConfigs: (query: string) => request<{ matches: ConfigSearchResult[] }>("/search/configs", { method: "POST", body: { query } }),

  logsStreamUrl: (query?: { tail?: number; level?: string; q?: string }) =>
    `/api/logs/stream${buildQuery(query)}`,
  nodeDownloadUrl: (id: number, oid?: string) => `/api/nodes/${id}/download${buildQuery({ oid })}`,
  logDownloadUrl: (query?: { since?: string; until?: string; level?: string; q?: string }) => `/api/logs/download${buildQuery(query)}`,
  configFileDownloadUrl: () => "/api/nodes/export.csv",
};

export type { ApiFieldError };
