export type Role = "admin" | "operator" | "viewer";
export type Theme = "light" | "dark" | "system";
export type NodeStatus = "ok" | "failed" | "pending" | "never";
export type OxidizedState = "online" | "offline" | "degraded" | "starting" | "unknown";
export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export type EffectiveSource =
  | "node"
  | "group_model"
  | "group"
  | "model"
  | "config"
  | "default"
  | "mixed"
  | "model_or_config"
  | "missing";

export interface EffectiveValue<T> {
  value: T | null;
  source: EffectiveSource;
  source_detail?: string | null;
}

export interface EffectiveSecret {
  set: boolean;
  source: EffectiveSource;
  source_detail?: string | null;
}

export interface NodeEffective {
  input: EffectiveValue<string>;
  port: EffectiveValue<string>;
  username: EffectiveValue<string>;
  password: EffectiveSecret;
  enable: EffectiveSecret;
  output: EffectiveValue<string>;
  timeout_seconds: EffectiveValue<number>;
  prompt: EffectiveValue<string>;
}

export interface Meta {
  setup_required: boolean;
  available_languages: string[];
  default_language: string;
  app_version: string;
  oidc_enabled?: boolean;
  timezone?: string | null;
  site_name?: string;
  logo_url?: string | null;
}

export interface User {
  id: number;
  username: string;
  full_name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  role: Role;
  language: string;
  theme: Theme;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
  last_login_at?: string | null;
  password_changed_at?: string;
}

export interface SessionPayload {
  user: User;
  csrf_token: string;
  capabilities: string[];
}

export interface SessionInfo {
  id: number;
  created_at: string | null;
  last_seen_at: string | null;
  expires_at: string | null;
  ip: string | null;
  user_agent: string | null;
  current: boolean;
}

export interface MfaChallenge {
  mfa_required: true;
  challenge_token: string;
  expires_at: string;
}

export interface MfaStatus {
  enabled: boolean;
  pending: boolean;
  recovery_codes_remaining: number;
}

export interface MfaSetup {
  secret: string;
  otpauth_uri: string;
}

export interface MfaEnableResult {
  recovery_codes: string[];
}

export interface Capabilities {
  capabilities: string[];
}

export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ApiFieldError {
  path: string;
  code: string;
  params?: Record<string, unknown>;
}

export interface ApiErrorPayload {
  error: {
    code: string;
    params?: Record<string, unknown>;
    fields?: ApiFieldError[];
    request_id?: string;
  };
}

export interface Node {
  id: number;
  name: string;
  address: string | null;
  model: string;
  group_name: string | null;
  status: NodeStatus;
  last_status_raw: string | null;
  last_backup_at: string | null;
  last_attempt_at: string | null;
  updated_at: string;
  warnings: string[];
  input?: string | null;
  port?: number | null;
  username?: string | null;
  has_password?: boolean;
  has_enable?: boolean;
  vars?: Record<string, unknown>;
  output?: string | null;
  prompt?: string | null;
  timeout_seconds?: number | null;
  effective?: NodeEffective;
}

export interface NodeListParams {
  search?: string;
  group?: string;
  model?: string;
  status?: NodeStatus;
  sort?: string;
  order?: "asc" | "desc";
  page?: number;
  page_size?: number;
}

export interface NodeInput {
  name: string;
  address?: string | null;
  model: string;
  group_name?: string | null;
  input?: string | null;
  port?: number | null;
  username?: string | null;
  password?: string | null;
  enable?: string | null;
  clear_password?: boolean;
  clear_enable?: boolean;
  vars?: Record<string, unknown> | null;
  output?: string | null;
  prompt?: string | null;
  timeout_seconds?: number | null;
}

export interface NodePingResult {
  reachable: boolean;
  address: string | null;
  sent: number;
  received: number;
  rtt_ms: number | null;
  message: string;
}

export interface NodeConnectionTest {
  ping: boolean;
  ping_rtt_ms: number | null;
  ping_message: string | null;
  tcp: boolean;
  ssh: boolean;
  authenticated: boolean;
  model_known: boolean;
  prompt: string | null;
  prompt_matches: boolean;
  message: string | null;
}

export interface NodeStatusDetail {
  node_id: number;
  status: NodeStatus;
  last_status_raw: string | null;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  observed_at: string | null;
  active_job_id: number | null;
  stale: boolean;
  warnings?: string[];
  last_error?: {
    code: string;
    params: Record<string, string>;
    error_class: string;
    at: string | null;
    crash?: {
      at: string | null;
      message: string | null;
      error_class: string | null;
      backtrace: string[];
    } | null;
  } | null;
}

export interface NodeCompare {
  left: { id: number; name: string };
  right: { id: number; name: string };
  diff: DiffResult;
}

export interface NodeHistoryItem {
  id: number;
  status: string;
  trigger: string;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
}

export interface NodeHistory {
  node_id: number;
  total: number;
  success_rate: number | null;
  items: NodeHistoryItem[];
}

export interface Version {
  oid: string;
  time: string | null;
  author: string | null;
  message: string | null;
}

export interface VersionsResponse {
  available: boolean;
  reason: string | null;
  versions: Version[];
}

export interface VersionContent {
  node_id: number;
  oid: string;
  time: string | null;
  content: string;
}

export interface DiffLine {
  line: number;
  text: string;
  segments?: { text: string; changed: boolean }[];
}

export interface DiffRow {
  left: DiffLine | null;
  right: DiffLine | null;
  type: "same" | "added" | "removed" | "changed";
}

export interface DiffResult {
  unified: string;
  side_by_side: DiffRow[];
  stats: { additions: number; deletions: number };
  from_name?: string;
  to_name?: string;
}

export interface NodeDiff extends DiffResult {
  node_id: number;
  from: { oid: string; time: string | null };
  to: { oid: string; time: string | null };
}

export interface GroupModelOverride {
  username?: string | null;
  has_password?: boolean;
  has_enable?: boolean;
  vars?: Record<string, unknown>;
  password?: string | null;
  clear_password?: boolean;
  enable?: string | null;
  clear_enable?: boolean;
  remove?: boolean;
}

export interface Group {
  name: string;
  node_count: number;
  username: string | null;
  has_password: boolean;
  has_enable: boolean;
  vars: Record<string, unknown>;
  models: Record<string, GroupModelOverride>;
  state: "applied" | "draft";
  draft: boolean;
  pending_removal?: boolean;
  requires_admin_apply?: boolean;
}

export interface GroupList {
  groups: Group[];
  draft_revision_id: number | null;
  requires_admin_apply: boolean;
  pending_apply?: boolean;
}

export interface GroupInput {
  name?: string;
  username?: string | null;
  password?: string | null;
  clear_password?: boolean;
  enable?: string | null;
  clear_enable?: boolean;
  vars?: Record<string, unknown>;
  models?: Record<string, GroupModelOverride>;
}

export interface Revision {
  id: number;
  parent_id: number | null;
  status: "draft" | "applied" | "superseded" | "discarded" | "rolled_back";
  origin: string;
  note: string | null;
  created_by_id: number | null;
  created_at: string;
  applied_by_id: number | null;
  applied_at: string | null;
  file_written_at: string | null;
  config_sha256: string;
  yaml_sha256: string;
}

export interface ConfigDrift {
  detected: boolean;
  expected_sha256: string | null;
  observed_sha256: string | null;
  file_exists: boolean;
  detected_at?: string | null;
}

export interface ConfigState {
  applied: Revision | null;
  draft: Revision | null;
  config: Record<string, unknown>;
  editable_yaml: string;
  effective_yaml_preview: string;
  managed_keys: string[];
  drift: ConfigDrift;
  requires_apply: boolean;
}

export interface ConfigValidation {
  config: Record<string, unknown>;
  editable_yaml: string;
  effective_yaml_preview: string;
  diff: DiffResult;
}

export interface ConfigRevisionDetail extends Revision {
  config: Record<string, unknown>;
  editable_yaml: string;
  effective_yaml_preview: string;
}

export interface ConfigDraftResponse {
  revision: ConfigRevisionDetail;
  diff: DiffResult;
  requires_apply: boolean;
}

export interface CatalogField {
  path: string;
  type: string;
  label_code: string;
  help_code: string;
  section: string;
  level: string;
  sensitive: boolean;
  managed: boolean;
  deprecated: boolean;
  default?: unknown;
  min?: number;
  max?: number;
  options?: unknown[] | string;
  placeholder?: string;
}

export interface CatalogVar {
  name: string;
  type: string;
  label_code: string;
  help_code: string;
  technical_description: string;
  options?: string[] | null;
}

export interface CatalogHookField extends CatalogField {}

export interface CatalogHook {
  name: string;
  label_code: string;
  help_code: string;
  technical_description: string;
  events: string[];
  suggested_events: string[];
  fields: CatalogHookField[];
}

export interface CatalogSection {
  id: string;
  label_code: string;
}

export interface Catalog {
  fields: CatalogField[];
  sections: CatalogSection[];
  models: string[];
  model_vendors: Record<string, string>;
  inputs: string[];
  outputs: string[];
  hook_types: Record<string, CatalogHook>;
  vars: CatalogVar[];
  managed_keys: string[];
  defaults: Record<string, unknown>;
}

export interface Job {
  id: number;
  kind: string;
  status: JobStatus;
  progress: { done: number; total: number };
  node_id: number | null;
  node_name: string | null;
  created_by: { id: number; username: string } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: { code: string; params?: Record<string, unknown> } | null;
  result: Record<string, unknown> | null;
}

export interface StatusPayload {
  oxidized: {
    state: OxidizedState;
    api_online: boolean;
    container_state: string | null;
    container_running: boolean;
    health: string | null;
    last_seen_at: string | null;
    version: string | null;
  };
  nodes: { total: number; ok: number; failed: number; pending: number; never: number };
  backups: { last_success_at: string | null; last_failure_at: string | null; active_jobs: number };
  activity: { date: string; success: number; failed: number }[];
  sla: { days: number; groups: { group: string; success: number; failed: number; rate: number | null }[] };
  warnings: string[];
}

export interface LogLine {
  seq: number;
  timestamp: string | null;
  stream: "stdout" | "stderr";
  level: "trace" | "debug" | "info" | "warn" | "error" | "fatal" | "unknown";
  text: string;
}

export interface LogSnapshot {
  lines: LogLine[];
  truncated: boolean;
}

export interface AuditEntry {
  id: number;
  actor: { user_id: number | null; username: string; role: string };
  action_code: string;
  action_params: Record<string, unknown>;
  target_type: string | null;
  target_id: string | null;
  ip: string | null;
  created_at: string;
}

export interface SystemSettings {
  oxidized_api_url: string;
  oxidized_container_name: string;
  docker_proxy_url: string;
  timezone: string | null;
  activity_retention_days: number;
  audit_retention_days: number;
  poll_interval_seconds: number;
  log_tail_default: number;
  config_backup_keep: number;
  password_min_length: number;
  password_require_complexity: boolean;
  password_history_count: number;
  login_max_failures_per_user: number;
  login_max_failures_per_ip: number;
  login_window_minutes: number;
  login_lockout_minutes: number;
  ip_allowlist: string;
  notify_webhook_url: string;
  notify_on_failure: boolean;
  notify_stale_hours: number;
  site_name: string;
  has_logo: boolean;
  environment: {
    oxidized_api_url: string;
    oxidized_container_name: string;
    docker_proxy_url: string;
  };
}

export type NotificationKind = "webhook" | "slack" | "discord" | "telegram";
export type NotificationEvent = "job.failed" | "backup.stale";

export interface NotificationChannel {
  id: number;
  name: string;
  kind: NotificationKind;
  enabled: boolean;
  events: NotificationEvent[];
  config: Record<string, string>;
  created_at: string | null;
  updated_at: string | null;
}

export interface ApiToken {
  id: number;
  name: string;
  prefix: string;
  role: "admin" | "operator" | "viewer";
  created_at: string | null;
  expires_at: string | null;
  last_used_at: string | null;
  revoked: boolean;
}

export interface BackupSchedule {
  id: number;
  group_name: string | null;
  interval_minutes: number;
  enabled: boolean;
  next_run_at: string | null;
  last_run_at: string | null;
  node_count: number;
}

export interface BackupScheduleGroup {
  name: string;
  node_count: number;
}

export interface BackupScheduleList {
  items: BackupSchedule[];
  groups: BackupScheduleGroup[];
  ungrouped_count: number;
  total_nodes: number;
  oxidized_interval_seconds: number | null;
}

export interface ScheduledApply {
  id: number;
  revision_id: number | null;
  run_at: string | null;
  status: "pending" | "running" | "applied" | "failed" | "cancelled";
  job_id: number | null;
  job_status: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error_code: string | null;
}

export interface SearchResults {
  nodes: { id: number; name: string; address: string | null; model: string; group_name: string | null }[];
  groups: { name: string }[];
}

export interface ConfigSearchResult {
  node_id: number;
  name: string;
  full_name: string;
  group_name: string | null;
  model: string;
}

export interface ImportSummary {
  created: number;
  updated: number;
  skipped: number;
  errors: { row: number; path?: string; code: string; params?: Record<string, unknown> }[];
  dry_run: boolean;
  reload_status: string;
  warnings: string[];
}
