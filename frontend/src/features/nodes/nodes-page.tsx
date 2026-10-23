import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, Download, Filter, MoreHorizontal, Network, Pencil, Plus, RefreshCw, Search, ServerCog, Trash2, Upload, UsersRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { PageHeader } from "@/components/shared/page-header";
import { Pagination } from "@/components/shared/pagination";
import { Spinner, TableSkeleton } from "@/components/shared/loaders";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { NodeStatusBadge } from "@/components/shared/status-badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DiffView } from "@/components/shared/diff-view";
import { NodeFormSheet } from "@/features/nodes/node-form-sheet";
import { NodeImportDialog } from "@/features/nodes/node-import-dialog";
import { useDebounce } from "@/hooks/use-debounce";
import { useIntl, usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { notifyError } from "@/lib/errors";
import { cn } from "@/lib/utils";
import type { Node, NodeListParams, NodeStatus } from "@/types/api";

type SortDirection = "asc" | "desc";

function SortHead({
  label,
  field,
  current,
  direction,
  onSort,
  className,
}: {
  label: string;
  field: string;
  current: string;
  direction: SortDirection;
  onSort: (field: string) => void;
  className?: string;
}) {
  const active = current === field;
  const Icon = !active ? ArrowUpDown : direction === "asc" ? ArrowUp : ArrowDown;
  return (
    <button
      type="button"
      onClick={() => onSort(field)}
      className={cn("inline-flex items-center gap-1.5 hover:text-foreground", active && "text-foreground", className)}
    >
      {label}
      <Icon className={cn("h-3 w-3", !active && "opacity-40")} />
    </button>
  );
}

export function NodesPage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const { can } = useAuth();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get("search") ?? "");
  const debouncedSearch = useDebounce(search, 300);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [formOpen, setFormOpen] = useState(false);
  const [editingNode, setEditingNode] = useState<number | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Node | null>(null);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [groupDialogOpen, setGroupDialogOpen] = useState(false);
  const [bulkGroup, setBulkGroup] = useState("");
  const [bulkEditOpen, setBulkEditOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);
  const [bulkModel, setBulkModel] = useState("");
  const [bulkInput, setBulkInput] = useState("");
  const [bulkPort, setBulkPort] = useState("");
  const [filterDialogOpen, setFilterDialogOpen] = useState(false);
  const [filterName, setFilterName] = useState("");
  const [savedFilters, setSavedFilters] = useState<{ name: string; query: string }[]>(() => {
    try {
      return JSON.parse(localStorage.getItem("oxidized-ui:node-filters") ?? "[]") as { name: string; query: string }[];
    } catch {
      return [];
    }
  });
  usePageTitle("nav.nodes");

  const page = Number(params.get("page") ?? "1") || 1;
  const group = params.get("group") ?? "";
  const model = params.get("model") ?? "";
  const status = (params.get("status") ?? "") as NodeStatus | "";
  const sort = params.get("sort") ?? "name";
  const order = (params.get("order") ?? "asc") as SortDirection;

  const setParam = (key: string, value: string | null, resetPage = true) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (resetPage) next.delete("page");
    setParams(next, { replace: true });
  };

  useEffect(() => {
    if (debouncedSearch !== (params.get("search") ?? "")) {
      setParam("search", debouncedSearch || null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  useEffect(() => {
    setSearch(params.get("search") ?? "");
  }, [params]);

  const query: NodeListParams = {
    search: params.get("search") ?? undefined,
    group: group || undefined,
    model: model || undefined,
    status: status || undefined,
    sort,
    order,
    page,
    page_size: 25,
  };

  const nodesQuery = useQuery({
    queryKey: ["nodes", query],
    queryFn: () => api.nodes(query),
    placeholderData: keepPreviousData,
  });
  const groupsQuery = useQuery({
    queryKey: ["groups"],
    queryFn: api.groups,
    enabled: can("groups.write"),
  });
  const catalogQuery = useQuery({
    queryKey: ["config-catalog"],
    queryFn: api.configCatalog,
    staleTime: 5 * 60_000,
  });

  const models = useMemo(() => {
    const catalogModels = catalogQuery.data?.models ?? [];
    const fromNodes = nodesQuery.data?.items.map((node) => node.model) ?? [];
    return Array.from(new Set([...catalogModels, ...fromNodes])).sort((a, b) => a.localeCompare(b));
  }, [catalogQuery.data?.models, nodesQuery.data?.items]);

  const groupNames = useMemo(() => {
    const names = new Set((groupsQuery.data?.groups ?? []).map((item) => item.name));
    (nodesQuery.data?.items ?? []).forEach((node) => {
      if (node.group_name) names.add(node.group_name);
    });
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }, [groupsQuery.data?.groups, nodesQuery.data?.items]);

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["nodes"] });
    await queryClient.invalidateQueries({ queryKey: ["status"] });
    await queryClient.invalidateQueries({ queryKey: ["jobs"] });
  };

  const backupOne = useMutation({
    mutationFn: (node: Node) => api.backupNode(node.id),
    onSuccess: (_job, node) => {
      toast.success(t("nodes.backupQueued", { name: node.name }));
      void invalidate();
    },
    onError: (error) => notifyError(t, error),
  });

  const deleteOne = useMutation({
    mutationFn: (node: Node) => api.deleteNode(node.id),
    onSuccess: () => {
      toast.success(t("nodes.deleteSuccess"));
      setDeleteTarget(null);
      setSelected(new Set());
      void invalidate();
    },
    onError: (error) => notifyError(t, error),
  });

  const compareIds = useMemo(() => Array.from(selected).slice(0, 2), [selected]);
  const compareQuery = useQuery({
    queryKey: ["node-compare", ...compareIds],
    queryFn: () => api.compareNodes(compareIds[0], compareIds[1]),
    enabled: compareOpen && compareIds.length === 2,
  });

  const bulkBackup = useMutation({
    mutationFn: () => api.bulkNodes({ action: "backup", ids: Array.from(selected) }),
    onSuccess: () => {
      toast.success(t("common.operationCompleted"));
      setSelected(new Set());
      void invalidate();
    },
    onError: (error) => notifyError(t, error),
  });

  const bulkDelete = useMutation({
    mutationFn: () => api.bulkNodes({ action: "delete", ids: Array.from(selected) }),
    onSuccess: () => {
      toast.success(t("nodes.bulkDeleteSuccess", { count: selected.size }));
      setBulkDeleteOpen(false);
      setSelected(new Set());
      void invalidate();
    },
    onError: (error) => notifyError(t, error),
  });

  const bulkEdit = useMutation({
    mutationFn: () =>
      api.bulkNodes({
        action: "update",
        ids: Array.from(selected),
        model: bulkModel.trim() || null,
        input: bulkInput.trim() || null,
        port: bulkPort ? Number(bulkPort) : null,
      }),
    onSuccess: () => {
      toast.success(t("nodes.bulkEditSuccess", { count: selected.size }));
      setBulkEditOpen(false);
      setSelected(new Set());
      void invalidate();
    },
    onError: (error) => notifyError(t, error),
  });

  const bulkChangeGroup = useMutation({
    mutationFn: () =>
      api.bulkNodes({ action: "change_group", ids: Array.from(selected), group_name: bulkGroup || null }),
    onSuccess: () => {
      toast.success(t("nodes.bulkGroupSuccess", { count: selected.size }));
      setGroupDialogOpen(false);
      setBulkGroup("");
      setSelected(new Set());
      void invalidate();
    },
    onError: (error) => notifyError(t, error),
  });

  const items = nodesQuery.data?.items ?? [];
  const allSelected = items.length > 0 && items.every((node) => selected.has(node.id));
  const someSelected = items.some((node) => selected.has(node.id));
  const hasFilters = Boolean(query.search || query.group || query.model || query.status);
  const availableGroups = (groupsQuery.data?.groups ?? []).filter((item) => item.state === "applied");

  const toggleAll = () => {
    if (allSelected) {
      const next = new Set(selected);
      items.forEach((node) => next.delete(node.id));
      setSelected(next);
    } else {
      const next = new Set(selected);
      items.forEach((node) => next.add(node.id));
      setSelected(next);
    }
  };

  useEffect(() => {
    setSelected(new Set());
  }, [page, group, model, status, params.get("search")]);

  const onSort = (field: string) => {
    const next = new URLSearchParams(params);
    const nextOrder = sort === field ? (order === "asc" ? "desc" : "asc") : "asc";
    next.set("sort", field);
    next.set("order", nextOrder);
    next.delete("page");
    setParams(next, { replace: true });
  };

  const persistFilters = (items: { name: string; query: string }[]) => {
    setSavedFilters(items);
    localStorage.setItem("oxidized-ui:node-filters", JSON.stringify(items));
  };
  const saveFilter = () => {
    const name = filterName.trim();
    if (!name) return;
    persistFilters([...savedFilters.filter((item) => item.name !== name), { name, query: params.toString() }]);
    setFilterName("");
    setFilterDialogOpen(false);
  };

  const clearFilters = () => {
    setSearch("");
    setParams(new URLSearchParams(), { replace: true });
  };

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={
          <>
            <Network className="h-3.5 w-3.5 text-primary" />
            {t("nav.inventory")}
          </>
        }
        title={t("nodes.title")}
        description={t("nodes.subtitle")}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => void api.exportNodes().then(() => toast.success(t("nodes.exportSuccess"))).catch((error) => notifyError(t, error))}>
              <Download />
              {t("nodes.downloadExport")}
            </Button>
            {can("nodes.write") ? (
              <>
                <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
                  <Upload />
                  {t("nodes.import")}
                </Button>
                <Button
                  size="sm"
                  onClick={() => {
                    setEditingNode(null);
                    setFormOpen(true);
                  }}
                >
                  <Plus />
                  {t("nodes.addNode")}
                </Button>
              </>
            ) : null}
          </>
        }
      />

      <div className="overflow-hidden rounded-lg border bg-card shadow-soft">
        <div className="flex flex-col gap-3 border-b p-3 lg:flex-row lg:items-center">
          <div className="relative min-w-0 flex-1 lg:max-w-sm">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("nodes.searchPlaceholder")}
              className="h-8 pl-8 text-xs"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={status || "__all__"} onValueChange={(value) => setParam("status", value === "__all__" ? null : value)}>
              <SelectTrigger className="h-8 w-[9.5rem] text-xs">
                <SelectValue placeholder={t("nodes.filterStatus")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">{t("nodes.allStatuses")}</SelectItem>
                {(["ok", "failed", "pending", "never"] as NodeStatus[]).map((value) => (
                  <SelectItem key={value} value={value}>
                    {t(`nodeStatus.${value}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {groupNames.length ? (
              <Select value={group || "__all__"} onValueChange={(value) => setParam("group", value === "__all__" ? null : value)}>
                <SelectTrigger className="h-8 w-[9.5rem] text-xs">
                  <SelectValue placeholder={t("nodes.filterGroup")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">{t("nodes.allGroups")}</SelectItem>
                  {groupNames.map((name) => (
                    <SelectItem key={name} value={name}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
            {models.length ? (
              <Select value={model || "__all__"} onValueChange={(value) => setParam("model", value === "__all__" ? null : value)}>
                <SelectTrigger className="h-8 w-[9.5rem] text-xs">
                  <SelectValue placeholder={t("nodes.filterModel")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all__">{t("nodes.allModels")}</SelectItem>
                  {models.map((name) => (
                    <SelectItem key={name} value={name}>
                      {name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
            {hasFilters ? (
              <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={clearFilters}>
                {t("common.clearFilters")}
              </Button>
            ) : null}
            <Button variant="outline" size="xs" onClick={() => setFilterDialogOpen(true)} disabled={!hasFilters}>
              <Filter />
              {t("nodes.saveFilter")}
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => void nodesQuery.refetch()}
              disabled={nodesQuery.isFetching}
              aria-label={t("common.refresh")}
              title={t("common.refresh")}
            >
              {nodesQuery.isFetching ? <Spinner /> : <RefreshCw />}
            </Button>
          </div>
        </div>

        {selected.size > 0 ? (
          <div className="flex flex-wrap items-center gap-2 border-b bg-primary/[0.04] px-3 py-2">
            <span className="mr-1 font-mono text-[10px] uppercase tracking-[0.1em] text-primary">
              {t("nodes.bulkSelected", { count: selected.size })}
            </span>
            {selected.size === 2 ? (
              <Button variant="outline" size="xs" onClick={() => setCompareOpen(true)}>
                <ArrowUpDown />
                {t("nodes.compare")}
              </Button>
            ) : null}
            {can("backups.trigger") ? (
              <Button variant="outline" size="xs" onClick={() => bulkBackup.mutate()} disabled={bulkBackup.isPending}>
                {bulkBackup.isPending ? <Spinner /> : <ServerCog />}
                {t("nodes.bulkBackup")}
              </Button>
            ) : null}
            {can("nodes.write") ? (
              <Button variant="outline" size="xs" onClick={() => setBulkEditOpen(true)}>
                <Pencil />
                {t("nodes.bulkEdit")}
              </Button>
            ) : null}
            {can("groups.write") ? (
              <Button variant="outline" size="xs" onClick={() => setGroupDialogOpen(true)}>
                <UsersRound />
                {t("nodes.bulkGroup")}
              </Button>
            ) : null}
            {can("nodes.write") ? (
              <Button variant="destructive-outline" size="xs" onClick={() => setBulkDeleteOpen(true)}>
                <Trash2 />
                {t("nodes.bulkDelete")}
              </Button>
            ) : null}
            <Button variant="ghost" size="xs" onClick={() => setSelected(new Set())}>
              {t("common.clear")}
            </Button>
          </div>
        ) : null}

        {nodesQuery.isLoading ? (
          <TableSkeleton rows={8} columns={6} />
        ) : nodesQuery.isError ? (
          <div className="p-4">
            <ErrorState onRetry={() => void nodesQuery.refetch()} compact />
          </div>
        ) : items.length === 0 ? (
          <div className="p-4">
            {hasFilters ? (
              <EmptyState
                icon={Search}
                title={t("nodes.noMatchTitle")}
                description={t("nodes.noMatchDescription")}
                action={<Button variant="outline" size="sm" onClick={clearFilters}>{t("common.clearFilters")}</Button>}
              />
            ) : (
              <EmptyState
                icon={Network}
                title={t("nodes.emptyTitle")}
                description={t("nodes.emptyDescription")}
                action={
                  can("nodes.write") ? (
                    <>
                      <Button size="sm" onClick={() => { setEditingNode(null); setFormOpen(true); }}>
                        <Plus />
                        {t("nodes.addNode")}
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => setImportOpen(true)}>
                        <Upload />
                        {t("nodes.import")}
                      </Button>
                    </>
                  ) : undefined
                }
              />
            )}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {can("nodes.write") ? (
                  <TableHead className="w-9">
                    <Checkbox
                      checked={allSelected ? true : someSelected ? "indeterminate" : false}
                      onCheckedChange={toggleAll}
                      aria-label={t("common.selectAll")}
                    />
                  </TableHead>
                ) : null}
                <TableHead>
                  <SortHead label={t("nodes.name")} field="name" current={sort} direction={order} onSort={onSort} />
                </TableHead>
                <TableHead className="hidden lg:table-cell">{t("nodes.address")}</TableHead>
                <TableHead>
                  <SortHead label={t("nodes.model")} field="model" current={sort} direction={order} onSort={onSort} />
                </TableHead>
                <TableHead className="hidden xl:table-cell">{t("nodes.group")}</TableHead>
                <TableHead>
                  <SortHead label={t("common.status")} field="status" current={sort} direction={order} onSort={onSort} />
                </TableHead>
                <TableHead className="hidden text-right lg:table-cell">
                  <SortHead label={t("nodes.lastBackup")} field="last_backup_at" current={sort} direction={order} onSort={onSort} className="justify-end" />
                </TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((node) => (
                <TableRow key={node.id} data-state={selected.has(node.id) ? "selected" : undefined}>
                  {can("nodes.write") ? (
                    <TableCell>
                      <Checkbox
                        checked={selected.has(node.id)}
                        onCheckedChange={(checked) => {
                          const next = new Set(selected);
                          if (checked) next.add(node.id);
                          else next.delete(node.id);
                          setSelected(next);
                        }}
                        aria-label={t("table.selectRow")}
                      />
                    </TableCell>
                  ) : null}
                  <TableCell>
                    <Link to={`/nodes/${node.id}`} className="group inline-flex items-center gap-2.5">
                      <span className="flex h-7 w-7 items-center justify-center rounded-md border bg-muted/20 text-muted-foreground">
                        <Network className="h-3.5 w-3.5" />
                      </span>
                      <span className="min-w-0">
                        <span className="block max-w-[16rem] truncate text-[13px] font-medium group-hover:text-primary">{node.name}</span>
                        <span className="block font-mono text-[9px] uppercase tracking-[0.08em] text-muted-foreground lg:hidden">
                          {node.address ?? "—"} · {node.model}
                        </span>
                      </span>
                    </Link>
                  </TableCell>
                  <TableCell className="hidden font-mono text-[11px] text-muted-foreground lg:table-cell">
                    {node.address ?? "—"}
                  </TableCell>
                  <TableCell>
                    <span className="rounded border bg-muted/30 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{node.model}</span>
                  </TableCell>
                  <TableCell className="hidden text-xs text-muted-foreground xl:table-cell">
                    {node.group_name ?? "—"}
                  </TableCell>
                  <TableCell><NodeStatusBadge status={node.status} /></TableCell>
                  <TableCell className="hidden text-right font-mono text-[10px] text-muted-foreground lg:table-cell">
                    {node.last_backup_at ? intl.relative(node.last_backup_at) : t("common.never")}
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon-xs" aria-label={t("common.more")}>
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem asChild>
                          <Link to={`/nodes/${node.id}`}>{t("common.open")}</Link>
                        </DropdownMenuItem>
                        {can("backups.trigger") ? (
                          <DropdownMenuItem onSelect={() => backupOne.mutate(node)} disabled={backupOne.isPending}>
                            <ServerCog />
                            {t("nodeDetail.backupNow")}
                          </DropdownMenuItem>
                        ) : null}
                        {can("nodes.write") ? (
                          <>
                            <DropdownMenuItem
                              onSelect={() => {
                                setEditingNode(node.id);
                                setFormOpen(true);
                              }}
                            >
                              <Pencil />
                              {t("common.edit")}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive focus:text-destructive"
                              onSelect={() => setDeleteTarget(node)}
                            >
                              <Trash2 />
                              {t("common.delete")}
                            </DropdownMenuItem>
                          </>
                        ) : null}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {nodesQuery.data ? (
          <Pagination
            page={nodesQuery.data.page}
            totalPages={nodesQuery.data.total_pages}
            total={nodesQuery.data.total}
            onPage={(next) => setParam("page", String(next), false)}
          />
        ) : null}
      </div>

      <NodeFormSheet
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open);
          if (!open) setEditingNode(null);
        }}
        nodeId={editingNode}
        onSaved={() => void invalidate()}
      />
      <NodeImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        onImported={() => void invalidate()}
      />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={t("nodes.deleteTitle")}
        description={t("nodes.deleteDescription", { name: deleteTarget?.name ?? "" })}
        confirmLabel={t("common.delete")}
        loading={deleteOne.isPending}
        onConfirm={() => deleteTarget && deleteOne.mutate(deleteTarget)}
      />
      <ConfirmDialog
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        title={t("nodes.bulkDeleteTitle")}
        description={t("nodes.bulkDeleteDescription", { count: selected.size })}
        confirmLabel={t("common.delete")}
        loading={bulkDelete.isPending}
        onConfirm={() => bulkDelete.mutate()}
      />

      <Dialog open={compareOpen} onOpenChange={setCompareOpen}>
        <DialogContent className="max-w-6xl">
          <DialogHeader>
            <DialogTitle>{t("nodes.compare")}</DialogTitle>
            <DialogDescription>{t("nodes.compareDescription")}</DialogDescription>
          </DialogHeader>
          {compareQuery.isLoading ? <div className="h-60 animate-pulse rounded-md bg-muted" /> : compareQuery.isError ? (
            <ErrorState onRetry={() => void compareQuery.refetch()} compact />
          ) : compareQuery.data ? (
            <DiffView diff={compareQuery.data.diff} fromLabel={compareQuery.data.left.name} toLabel={compareQuery.data.right.name} />
          ) : null}
        </DialogContent>
      </Dialog>
      <Dialog open={bulkEditOpen} onOpenChange={setBulkEditOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("nodes.bulkEditTitle")}</DialogTitle>
            <DialogDescription>{t("nodes.bulkEditDescription", { count: selected.size })}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1">
              <Label>{t("nodes.model")}</Label>
              <Input value={bulkModel} onChange={(event) => setBulkModel(event.target.value)} placeholder="ios" />
            </div>
            <div className="space-y-1">
              <Label>{t("nodes.input")}</Label>
              <Input value={bulkInput} onChange={(event) => setBulkInput(event.target.value)} placeholder="ssh" />
            </div>
            <div className="space-y-1">
              <Label>{t("nodes.port")}</Label>
              <Input type="number" min={1} max={65535} value={bulkPort} onChange={(event) => setBulkPort(event.target.value)} placeholder="22" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBulkEditOpen(false)}>{t("common.cancel")}</Button>
            <Button onClick={() => bulkEdit.mutate()} disabled={bulkEdit.isPending || (!bulkModel.trim() && !bulkInput.trim() && !bulkPort)}>
              {bulkEdit.isPending ? <Spinner /> : <Pencil />}
              {t("common.apply")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={groupDialogOpen} onOpenChange={setGroupDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("nodes.bulkGroupTitle")}</DialogTitle>
            <DialogDescription>{t("nodes.bulkGroupDescription")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>{t("nodes.group")}</Label>
            <Select value={bulkGroup} onValueChange={setBulkGroup}>
              <SelectTrigger>
                <SelectValue placeholder={t("nodeForm.noGroup")} />
              </SelectTrigger>
              <SelectContent>
                {availableGroups.map((item) => (
                  <SelectItem key={item.name} value={item.name}>
                    {item.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGroupDialogOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => bulkChangeGroup.mutate()} disabled={!bulkGroup || bulkChangeGroup.isPending}>
              {bulkChangeGroup.isPending ? <Spinner /> : <ChevronDown />}
              {t("common.apply")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={filterDialogOpen} onOpenChange={setFilterDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("nodes.saveFilter")}</DialogTitle>
            <DialogDescription>{t("nodes.saveFilterDescription")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="filter-name">{t("nodes.filterName")}</Label>
            <Input id="filter-name" value={filterName} onChange={(event) => setFilterName(event.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setFilterDialogOpen(false)}>{t("common.cancel")}</Button>
            <Button onClick={saveFilter} disabled={!filterName.trim()}>{t("common.save")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
