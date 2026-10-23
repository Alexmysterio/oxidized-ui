import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { KeyRound, MoreHorizontal, Plus, Search, ShieldCheck, Trash2, UserCog, UsersRound } from "lucide-react";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { z } from "zod";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { Pagination } from "@/components/shared/pagination";
import { PageHeader } from "@/components/shared/page-header";
import { PasswordInput } from "@/components/shared/password-input";
import { Spinner, TableSkeleton } from "@/components/shared/loaders";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useIntl, usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage, notifyError } from "@/lib/errors";
import { passwordSchema, userSchema } from "@/lib/validation";
import type { Role, User } from "@/types/api";

interface CreateValues {
  username: string;
  password: string;
  role: Role;
  language: string;
}

function UserDialog({
  open,
  onOpenChange,
  user,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User | null;
}) {
  const { t } = useTranslation();
  const { meta } = useAuth();
  const queryClient = useQueryClient();
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const languages = meta?.available_languages?.length ? meta.available_languages : ["es", "en"];

  const createForm = useForm<CreateValues>({
    resolver: zodResolver(userSchema(t)),
    defaultValues: { username: "", password: "", role: "operator", language: "es" },
  });

  const editSchema = z.object({
    role: z.enum(["admin", "operator", "viewer"]),
    language: z.string().min(1),
    is_active: z.boolean(),
  });
  const editForm = useForm<{ role: Role; language: string; is_active: boolean }>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      role: user?.role ?? "operator",
      language: user?.language ?? "es",
      is_active: user?.is_active ?? true,
    },
  });

  useEffect(() => {
    if (!open) return;
    setServerError(null);
    if (user) {
      editForm.reset({
        role: user.role,
        language: user.language,
        is_active: user.is_active ?? true,
      });
    } else {
      createForm.reset({
        username: "",
        password: "",
        role: "operator",
        language: meta?.default_language ?? "es",
      });
    }
  }, [open, user, meta?.default_language, createForm, editForm]);

  const submit = async () => {
    setServerError(null);
    setSubmitting(true);
    try {
      if (user) {
        if (!(await editForm.trigger())) {
          setSubmitting(false);
          return;
        }
        const values = editForm.getValues();
        await api.updateUser(user.id, values);
        toast.success(t("users.updated"));
      } else {
        if (!(await createForm.trigger())) {
          setSubmitting(false);
          return;
        }
        const values = createForm.getValues();
        await api.createUser(values);
        toast.success(t("users.created"));
      }
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      onOpenChange(false);
    } catch (error) {
      setServerError(errorMessage(t, error));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{user ? t("users.editTitle") : t("users.createTitle")}</DialogTitle>
          <DialogDescription>{user ? t("users.editDescription") : t("users.createDescription")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {serverError ? <p className="rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">{serverError}</p> : null}
          {user ? (
            <>
              <div className="space-y-2">
                <Label>{t("users.username")}</Label>
                <Input value={user.username} disabled />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>{t("users.role")}</Label>
                  <Select value={editForm.watch("role")} onValueChange={(value) => editForm.setValue("role", value as Role)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {(["admin", "operator", "viewer"] as Role[]).map((role) => (
                        <SelectItem key={role} value={role}>{t(`roles.${role}`)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-[10px] text-muted-foreground">{t(`roles.${editForm.watch("role")}Description`)}</p>
                </div>
                <div className="space-y-2">
                  <Label>{t("users.language")}</Label>
                  <Select value={editForm.watch("language")} onValueChange={(value) => editForm.setValue("language", value)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {languages.map((language) => <SelectItem key={language} value={language}>{t(`languages.${language}`)}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex items-center justify-between rounded-md border p-3">
                <div>
                  <p className="text-xs font-medium">{t("users.active")}</p>
                  <p className="mt-0.5 text-[10px] text-muted-foreground">{t("users.editDescription")}</p>
                </div>
                <Switch checked={editForm.watch("is_active")} onCheckedChange={(value) => editForm.setValue("is_active", value)} />
              </div>
            </>
          ) : (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void submit();
              }}
              className="space-y-4"
              noValidate
            >
              <div className="space-y-2">
                <Label htmlFor="user-username">{t("users.username")}</Label>
                <Input id="user-username" autoComplete="off" {...createForm.register("username")} />
                {createForm.formState.errors.username ? <p className="text-xs text-destructive">{createForm.formState.errors.username.message}</p> : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="user-password">{t("auth.password")}</Label>
                <PasswordInput id="user-password" autoComplete="new-password" {...createForm.register("password")} />
                <p className="text-[10px] text-muted-foreground">{t("auth.passwordHint")}</p>
                {createForm.formState.errors.password ? <p className="text-xs text-destructive">{createForm.formState.errors.password.message}</p> : null}
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label>{t("users.role")}</Label>
                  <Select value={createForm.watch("role")} onValueChange={(value) => createForm.setValue("role", value as Role)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {(["admin", "operator", "viewer"] as Role[]).map((role) => (
                        <SelectItem key={role} value={role}>{t(`roles.${role}`)}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>{t("users.language")}</Label>
                  <Select value={createForm.watch("language")} onValueChange={(value) => createForm.setValue("language", value)}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {languages.map((language) => <SelectItem key={language} value={language}>{t(`languages.${language}`)}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </form>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>{t("common.cancel")}</Button>
          <Button onClick={() => void submit()} disabled={submitting}>
            {submitting ? <Spinner /> : <UserCog />}
            {submitting ? t("common.saving") : t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResetPasswordDialog({
  user,
  onOpenChange,
}: {
  user: User | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => {
    setPassword("");
    setError(null);
  }, [user?.id]);
  if (!user) return null;
  const submit = async () => {
    const parsed = passwordSchema(t, user.username).safeParse(password);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? t("errors.generic"));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.resetUserPassword(user.id, password);
      toast.success(t("users.resetDone"));
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      onOpenChange(false);
      setPassword("");
    } catch (caught) {
      setError(errorMessage(t, caught));
    } finally {
      setSubmitting(false);
    }
  };
  return (
    <Dialog open={Boolean(user)} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("users.passwordTitle")}</DialogTitle>
          <DialogDescription>{t("users.passwordDescription")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="reset-password">{t("users.newPassword")}</Label>
          <PasswordInput id="reset-password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" />
          {error ? <p className="text-xs text-destructive">{error}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>{t("common.cancel")}</Button>
          <Button onClick={() => void submit()} disabled={submitting}>{submitting ? <Spinner /> : <KeyRound />}{t("users.resetPassword")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function UsersPage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [resetTarget, setResetTarget] = useState<User | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);
  usePageTitle("nav.users");

  const usersQuery = useQuery({
    queryKey: ["users", page, search],
    queryFn: () => api.users({ page, page_size: 25, search: search || undefined }),
    placeholderData: keepPreviousData,
  });

  const remove = useMutation({
    mutationFn: (target: User) => api.deleteUser(target.id),
    onSuccess: () => {
      toast.success(t("users.deleted"));
      setDeleteTarget(null);
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const items = usersQuery.data?.items ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={<><ShieldCheck className="h-3.5 w-3.5 text-primary" />{t("nav.administration")}</>}
        title={t("users.title")}
        description={t("users.subtitle")}
        actions={
          <Button size="sm" onClick={() => { setEditing(null); setDialogOpen(true); }}>
            <Plus />
            {t("users.addUser")}
          </Button>
        }
      />
      <div className="overflow-hidden rounded-lg border bg-card shadow-soft">
        <div className="flex items-center gap-3 border-b p-3">
          <div className="relative max-w-sm flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(event) => { setSearch(event.target.value); setPage(1); }} placeholder={t("common.searchPlaceholder")} className="h-8 pl-8 text-xs" />
          </div>
          <p className="ml-auto hidden text-[10px] text-muted-foreground sm:block">{t("users.rolesHelp")}</p>
        </div>
        {usersQuery.isLoading ? (
          <TableSkeleton rows={6} columns={5} />
        ) : usersQuery.isError ? (
          <div className="p-4"><ErrorState onRetry={() => void usersQuery.refetch()} compact /></div>
        ) : items.length === 0 ? (
          <div className="p-4"><EmptyState icon={UsersRound} title={t("users.emptyTitle")} description={t("users.emptyDescription")} compact /></div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("users.username")}</TableHead>
                <TableHead>{t("users.role")}</TableHead>
                <TableHead>{t("common.status")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("users.lastLogin")}</TableHead>
                <TableHead className="hidden xl:table-cell">{t("users.createdAt")}</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((user) => (
                <TableRow key={user.id}>
                  <TableCell>
                    <div className="flex items-center gap-2.5">
                      <span className="flex h-7 w-7 items-center justify-center rounded-md border bg-primary/[0.04] font-mono text-[10px] text-primary">
                        {user.username.slice(0, 2).toUpperCase()}
                      </span>
                      <div>
                        <span className="block text-[13px] font-medium">{user.username}</span>
                        {currentUser?.id === user.id ? <span className="text-[10px] text-muted-foreground">{t("users.self")}</span> : null}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell><Badge variant={user.role === "admin" ? "default" : "secondary"}>{t(`roles.${user.role}`)}</Badge></TableCell>
                  <TableCell><Badge variant={user.is_active === false ? "outline" : "success"}>{user.is_active === false ? t("users.inactive") : t("users.active")}</Badge></TableCell>
                  <TableCell className="hidden text-xs text-muted-foreground lg:table-cell">{user.last_login_at ? intl.dateTime(user.last_login_at) : t("common.never")}</TableCell>
                  <TableCell className="hidden text-xs text-muted-foreground xl:table-cell">{user.created_at ? intl.date(user.created_at) : "—"}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild><Button variant="ghost" size="icon-xs" aria-label={t("common.more")}><MoreHorizontal /></Button></DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onSelect={() => { setEditing(user); setDialogOpen(true); }}><UserCog />{t("common.edit")}</DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => setResetTarget(user)}><KeyRound />{t("users.resetPassword")}</DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          disabled={currentUser?.id === user.id}
                          onSelect={() => setDeleteTarget(user)}
                        >
                          <Trash2 />{t("common.delete")}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        {usersQuery.data ? <Pagination page={usersQuery.data.page} totalPages={usersQuery.data.total_pages} total={usersQuery.data.total} onPage={setPage} /> : null}
      </div>

      <UserDialog key={editing?.id ?? "new"} open={dialogOpen} onOpenChange={setDialogOpen} user={editing} />
      <ResetPasswordDialog user={resetTarget} onOpenChange={(open) => !open && setResetTarget(null)} />
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title={t("users.deleteTitle")}
        description={t("users.deleteDescription", { username: deleteTarget?.username ?? "" })}
        confirmLabel={t("common.delete")}
        loading={remove.isPending}
        onConfirm={() => deleteTarget && remove.mutate(deleteTarget)}
      />
    </div>
  );
}
