import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, KeyRound, LogOut, Monitor, Moon, Palette, ShieldCheck, Sun, Trash2, Upload, UserRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { PageHeader } from "@/components/shared/page-header";
import { PasswordInput } from "@/components/shared/password-input";
import { CopyButton } from "@/components/shared/copy-button";
import { Spinner } from "@/components/shared/loaders";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useIntl, usePageTitle } from "@/hooks/use-app";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { errorMessage, notifyError } from "@/lib/errors";
import { changeLanguage } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import { passwordChangeSchema } from "@/lib/validation";
import { cn } from "@/lib/utils";
import type { MfaSetup, Theme } from "@/types/api";

interface PasswordValues {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export function ProfilePage() {
  const { t } = useTranslation();
  const intl = useIntl();
  const { user, meta, updateUser, applySession } = useAuth();
  const { theme, setTheme } = useTheme();
  const queryClient = useQueryClient();
  const [language, setLanguage] = useState(user?.language ?? "es");
  const [selectedTheme, setSelectedTheme] = useState<Theme>(theme);
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [email, setEmail] = useState(user?.email ?? "");
  const [savingProfile, setSavingProfile] = useState(false);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const avatarInput = useRef<HTMLInputElement | null>(null);
  const [savingPreferences, setSavingPreferences] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [mfaSetup, setMfaSetup] = useState<MfaSetup | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [disableOpen, setDisableOpen] = useState(false);
  const [disablePassword, setDisablePassword] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [disableError, setDisableError] = useState<string | null>(null);
  const [tokenName, setTokenName] = useState("");
  const [tokenRole, setTokenRole] = useState("viewer");
  const [tokenDays, setTokenDays] = useState(90);
  const [newToken, setNewToken] = useState<string | null>(null);
  usePageTitle("nav.profile");

  const languages = meta?.available_languages?.length ? meta.available_languages : ["es", "en"];
  const themes: { value: Theme; icon: typeof Sun }[] = [
    { value: "light", icon: Sun },
    { value: "dark", icon: Moon },
    { value: "system", icon: Monitor },
  ];

  useEffect(() => {
    if (user?.language) setLanguage(user.language);
  }, [user?.language]);

  useEffect(() => {
    setFullName(user?.full_name ?? "");
    setEmail(user?.email ?? "");
  }, [user?.full_name, user?.email]);

  useEffect(() => {
    setSelectedTheme(theme);
  }, [theme]);

  const form = useForm<PasswordValues>({
    resolver: zodResolver(passwordChangeSchema(t)),
    defaultValues: { current_password: "", new_password: "", confirm_password: "" },
  });

  const savePreferences = async () => {
    setSavingPreferences(true);
    try {
      const result = await api.updateMe({ language, theme: selectedTheme });
      updateUser(result.user);
      await changeLanguage(language, { persist: true });
      setTheme(selectedTheme, { persist: true });
      toast.success(t("profile.preferencesSaved"));
    } catch (error) {
      notifyError(t, error);
    } finally {
      setSavingPreferences(false);
    }
  };

  const saveProfile = async () => {
    setSavingProfile(true);
    try {
      const result = await api.updateMe({
        full_name: fullName.trim() || null,
        email: email.trim() || null,
      });
      updateUser(result.user);
      toast.success(t("profile.profileSaved"));
    } catch (error) {
      notifyError(t, error);
    } finally {
      setSavingProfile(false);
    }
  };

  const uploadAvatar = async (file?: File) => {
    if (!file) return;
    setAvatarBusy(true);
    try {
      const result = await api.uploadAvatar(file);
      updateUser(result.user);
      toast.success(t("profile.avatarSaved"));
    } catch (error) {
      notifyError(t, error);
    } finally {
      setAvatarBusy(false);
      if (avatarInput.current) avatarInput.current.value = "";
    }
  };

  const removeAvatar = async () => {
    if (!user) return;
    setAvatarBusy(true);
    try {
      await api.deleteAvatar();
      updateUser({ ...user, avatar_url: null });
      toast.success(t("profile.avatarRemoved"));
    } catch (error) {
      notifyError(t, error);
    } finally {
      setAvatarBusy(false);
    }
  };

  const changePassword = useMutation({
    mutationFn: (values: PasswordValues) => api.changePassword(values.current_password, values.new_password),
    onSuccess: async (session) => {
      await applySession(session);
      toast.success(t("profile.passwordChanged"));
      form.reset();
      setPasswordError(null);
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (error) => setPasswordError(errorMessage(t, error)),
  });

  const sessionsQuery = useQuery({
    queryKey: ["sessions"],
    queryFn: api.sessions,
    enabled: Boolean(user),
  });

  const revokeSession = useMutation({
    mutationFn: (id: number) => api.revokeSession(id),
    onSuccess: () => {
      toast.success(t("profile.sessionRevoked"));
      void queryClient.invalidateQueries({ queryKey: ["sessions"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const mfaStatusQuery = useQuery({
    queryKey: ["mfa"],
    queryFn: api.mfaStatus,
    enabled: user?.role === "admin",
  });

  const startMfa = useMutation({
    mutationFn: api.mfaSetup,
    onSuccess: (setup) => {
      setMfaSetup(setup);
      setMfaCode("");
      setRecoveryCodes(null);
    },
    onError: (error) => notifyError(t, error),
  });

  const enableMfa = useMutation({
    mutationFn: () => api.mfaEnable(mfaCode.trim()),
    onSuccess: (result) => {
      setRecoveryCodes(result.recovery_codes);
      setMfaSetup(null);
      setMfaCode("");
      toast.success(t("profile.mfaEnabledToast"));
      void queryClient.invalidateQueries({ queryKey: ["mfa"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const disableMfa = useMutation({
    mutationFn: () => api.mfaDisable(disablePassword, disableCode.trim()),
    onSuccess: () => {
      setDisableOpen(false);
      setDisablePassword("");
      setDisableCode("");
      setDisableError(null);
      toast.success(t("profile.mfaDisabledToast"));
      void queryClient.invalidateQueries({ queryKey: ["mfa"] });
    },
    onError: (error) => setDisableError(errorMessage(t, error)),
  });

  const tokensQuery = useQuery({
    queryKey: ["api-tokens"],
    queryFn: api.apiTokens,
    enabled: Boolean(user),
  });

  const createToken = useMutation({
    mutationFn: () => api.createApiToken(tokenName.trim(), tokenRole, tokenDays),
    onSuccess: (result) => {
      setNewToken(result.token);
      setTokenName("");
      toast.success(t("profile.tokenCreated"));
      void queryClient.invalidateQueries({ queryKey: ["api-tokens"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const revokeToken = useMutation({
    mutationFn: (id: number) => api.revokeApiToken(id),
    onSuccess: () => {
      toast.success(t("profile.tokenRevoked"));
      void queryClient.invalidateQueries({ queryKey: ["api-tokens"] });
    },
    onError: (error) => notifyError(t, error),
  });

  const submitPassword = form.handleSubmit((values) => changePassword.mutate(values));

  if (!user) return null;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow={<><UserRound className="h-3.5 w-3.5 text-primary" />{t("nav.profile")}</>}
        title={t("profile.title")}
        description={t("profile.subtitle")}
      />

      <div className="grid gap-4 xl:grid-cols-[1fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle>{t("profile.account")}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap items-center gap-4">
              <span className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-primary/20 bg-primary/[0.06] font-mono text-base font-semibold text-primary">
                {user.avatar_url ? (
                  <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
                ) : (
                  (user.full_name || user.username).slice(0, 2).toUpperCase()
                )}
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{user.full_name || user.username}</p>
                <p className="truncate text-[11px] text-muted-foreground">@{user.username}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <input
                    ref={avatarInput}
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    className="hidden"
                    onChange={(event) => void uploadAvatar(event.target.files?.[0])}
                  />
                  <Button type="button" variant="outline" size="xs" onClick={() => avatarInput.current?.click()} disabled={avatarBusy}>
                    {avatarBusy ? <Spinner /> : <Upload />}
                    {t("profile.changeAvatar")}
                  </Button>
                  {user.avatar_url ? (
                    <Button type="button" variant="ghost" size="xs" onClick={() => void removeAvatar()} disabled={avatarBusy}>
                      <Trash2 />
                      {t("profile.removeAvatar")}
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>

            <div className="grid gap-4 border-t pt-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="profile-full-name">{t("profile.fullName")}</Label>
                <Input
                  id="profile-full-name"
                  value={fullName}
                  maxLength={128}
                  onChange={(event) => setFullName(event.target.value)}
                  placeholder={t("profile.fullNamePlaceholder")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="profile-email">{t("profile.email")}</Label>
                <Input
                  id="profile-email"
                  type="email"
                  value={email}
                  maxLength={254}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder={t("profile.emailPlaceholder")}
                />
              </div>
            </div>
            <div className="flex justify-end">
              <Button type="button" size="sm" onClick={() => void saveProfile()} disabled={savingProfile}>
                {savingProfile ? <Spinner /> : <Check />}
                {t("profile.saveProfile")}
              </Button>
            </div>

            <div className="space-y-2 border-t pt-4 text-xs">
              <div className="flex justify-between gap-3"><span className="text-muted-foreground">{t("profile.username")}</span><span className="font-mono">{user.username}</span></div>
              <div className="flex justify-between gap-3"><span className="text-muted-foreground">{t("profile.role")}</span><span>{t(`roles.${user.role}`)}</span></div>
              <div className="flex justify-between gap-3"><span className="text-muted-foreground">{t("profile.lastLogin")}</span><span className="font-mono text-[10px]">{user.last_login_at ? intl.dateTime(user.last_login_at) : "—"}</span></div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Palette className="h-4 w-4 text-primary" />{t("profile.appearance")}</CardTitle>
            <CardDescription>{t("profile.appearanceDescription")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>{t("profile.language")}</Label>
                <Select value={language} onValueChange={setLanguage}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {languages.map((code) => <SelectItem key={code} value={code}>{t(`languages.${code}`)}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>{t("profile.theme")}</Label>
                <div className="grid grid-cols-3 gap-1.5">
                  {themes.map(({ value, icon: Icon }) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => {
                        setSelectedTheme(value);
                        setTheme(value, { persist: false });
                      }}
                      className={cn(
                        "flex flex-col items-center gap-1.5 rounded-md border px-2 py-2.5 text-[10px] transition-colors",
                        selectedTheme === value ? "border-primary/40 bg-primary/[0.06] text-foreground" : "text-muted-foreground hover:border-foreground/15",
                      )}
                    >
                      <Icon className="h-4 w-4" />
                      {t(`theme.${value}`)}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <Button size="sm" onClick={() => void savePreferences()} disabled={savingPreferences}>
              {savingPreferences ? <Spinner /> : <Check />}
              {t("profile.savePreferences")}
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" />{t("profile.security")}</CardTitle>
          <CardDescription>{t("profile.securityDescription")}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submitPassword} className="max-w-2xl space-y-4" noValidate>
            {passwordError ? <p className="rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">{passwordError}</p> : null}
            <div className="space-y-2">
              <Label htmlFor="current-password">{t("profile.currentPassword")}</Label>
              <PasswordInput id="current-password" autoComplete="current-password" {...form.register("current_password")} />
              {form.formState.errors.current_password ? <p className="text-xs text-destructive">{form.formState.errors.current_password.message}</p> : null}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="new-password">{t("profile.newPassword")}</Label>
                <PasswordInput id="new-password" autoComplete="new-password" {...form.register("new_password")} />
                {form.formState.errors.new_password ? <p className="text-xs text-destructive">{form.formState.errors.new_password.message}</p> : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirm-password">{t("profile.confirmPassword")}</Label>
                <PasswordInput id="confirm-password" autoComplete="new-password" {...form.register("confirm_password")} />
                {form.formState.errors.confirm_password ? <p className="text-xs text-destructive">{form.formState.errors.confirm_password.message}</p> : null}
              </div>
            </div>
            <Button type="submit" size="sm" disabled={changePassword.isPending}>
              {changePassword.isPending ? <Spinner /> : <KeyRound />}
              {t("profile.changePassword")}
            </Button>
          </form>
        </CardContent>
      </Card>

      {user.role === "admin" ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" />{t("profile.mfa")}</CardTitle>
            <CardDescription>{t("profile.mfaDescription")}</CardDescription>
          </CardHeader>
          <CardContent>
            {mfaStatusQuery.isLoading ? (
              <div className="h-12 animate-pulse rounded-md bg-muted" />
            ) : mfaStatusQuery.data?.enabled ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="space-y-1">
                  <Badge variant="success">{t("profile.mfaEnabled")}</Badge>
                  <p className="text-xs text-muted-foreground">
                    {t("profile.mfaRecoveryRemaining", { count: mfaStatusQuery.data.recovery_codes_remaining })}
                  </p>
                </div>
                <Button type="button" variant="outline" size="sm" onClick={() => setDisableOpen(true)}>
                  {t("profile.mfaDisable")}
                </Button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <Badge variant="outline">{t("profile.mfaDisabled")}</Badge>
                <Button type="button" size="sm" onClick={() => startMfa.mutate()} disabled={startMfa.isPending}>
                  {startMfa.isPending ? <Spinner /> : <KeyRound />}
                  {t("profile.mfaEnable")}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Monitor className="h-4 w-4 text-primary" />{t("profile.sessions")}</CardTitle>
          <CardDescription>{t("profile.sessionsDescription")}</CardDescription>
        </CardHeader>
        <CardContent>
          {sessionsQuery.isLoading ? (
            <div className="h-24 animate-pulse rounded-md bg-muted" />
          ) : sessionsQuery.isError ? (
            <div className="flex items-center justify-between gap-3 rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
              {t("profile.sessionsLoadFailed")}
              <Button type="button" variant="outline" size="sm" onClick={() => void sessionsQuery.refetch()}>
                {t("common.retry")}
              </Button>
            </div>
          ) : (
            <div className="divide-y">
              {(sessionsQuery.data?.sessions ?? []).map((session) => (
                <div key={session.id} className="flex flex-wrap items-start justify-between gap-3 py-3 first:pt-0 last:pb-0">
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs">{session.ip ?? t("profile.unknownIp")}</span>
                      {session.current ? <Badge variant="secondary">{t("profile.currentSession")}</Badge> : null}
                    </div>
                    <p className="max-w-xl truncate text-[11px] text-muted-foreground" title={session.user_agent ?? undefined}>
                      {session.user_agent || t("profile.unknownDevice")}
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      {t("profile.sessionCreated")}: {session.created_at ? intl.dateTime(session.created_at) : "—"}
                      {" · "}
                      {t("profile.sessionLastSeen")}: {session.last_seen_at ? intl.relative(session.last_seen_at) : "—"}
                      {" · "}
                      {t("profile.sessionExpires")}: {session.expires_at ? intl.dateTime(session.expires_at) : "—"}
                    </p>
                  </div>
                  {session.current ? null : (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-muted-foreground hover:text-destructive"
                      disabled={revokeSession.isPending}
                      onClick={() => revokeSession.mutate(session.id)}
                    >
                      <LogOut />
                      {t("profile.revokeSession")}
                    </Button>
                  )}
                </div>
              ))}
              {(sessionsQuery.data?.sessions ?? []).length === 0 ? (
                <p className="py-3 text-xs text-muted-foreground">{t("profile.noSessions")}</p>
              ) : null}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><KeyRound className="h-4 w-4 text-primary" />{t("profile.apiTokens")}</CardTitle>
          <CardDescription>{t("profile.apiTokensDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-2">
            <div className="space-y-1">
              <Label htmlFor="token-name">{t("profile.tokenName")}</Label>
              <Input id="token-name" value={tokenName} onChange={(event) => setTokenName(event.target.value)} className="w-44" />
            </div>
            <div className="space-y-1">
              <Label>{t("profile.tokenRole")}</Label>
              <Select value={tokenRole} onValueChange={setTokenRole}>
                <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="viewer">{t("roles.viewer")}</SelectItem>
                  <SelectItem value="operator">{t("roles.operator")}</SelectItem>
                  {user.role === "admin" ? <SelectItem value="admin">{t("roles.admin")}</SelectItem> : null}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="token-days">{t("profile.tokenDays")}</Label>
              <Input id="token-days" type="number" min={1} max={365} value={tokenDays} onChange={(event) => setTokenDays(Number(event.target.value))} className="w-24" />
            </div>
            <Button type="button" size="sm" onClick={() => createToken.mutate()} disabled={!tokenName.trim() || createToken.isPending}>
              {createToken.isPending ? <Spinner /> : <KeyRound />}
              {t("profile.createToken")}
            </Button>
          </div>
          {newToken ? (
            <div className="space-y-2 rounded-md border border-primary/20 bg-primary/[0.04] p-3">
              <p className="text-xs font-medium">{t("profile.tokenOnlyOnce")}</p>
              <div className="flex items-center gap-2">
                <Input readOnly value={newToken} className="font-mono text-xs" />
                <CopyButton value={newToken} />
              </div>
            </div>
          ) : null}
          <div className="divide-y">
            {(tokensQuery.data?.items ?? []).filter((item) => !item.revoked).map((item) => (
              <div key={item.id} className="flex items-center justify-between gap-2 py-2 text-xs">
                <span className="font-mono">{item.name} · {item.prefix} · {item.role} · {item.expires_at ? intl.dateTime(item.expires_at) : "—"}</span>
                <Button type="button" variant="ghost" size="sm" className="text-muted-foreground hover:text-destructive" onClick={() => revokeToken.mutate(item.id)}>
                  <Trash2 />
                  {t("profile.revokeToken")}
                </Button>
              </div>
            ))}
            {(tokensQuery.data?.items ?? []).filter((item) => !item.revoked).length === 0 ? <p className="text-xs text-muted-foreground">{t("profile.noTokens")}</p> : null}
          </div>
        </CardContent>
      </Card>

      <Dialog
        open={Boolean(mfaSetup) || Boolean(recoveryCodes)}
        onOpenChange={(open) => {
          if (!open) {
            setMfaSetup(null);
            setRecoveryCodes(null);
            setMfaCode("");
          }
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{recoveryCodes ? t("profile.mfaRecoveryTitle") : t("profile.mfaSetupTitle")}</DialogTitle>
            <DialogDescription>
              {recoveryCodes ? t("profile.mfaRecoveryDescription") : t("profile.mfaSetupDescription")}
            </DialogDescription>
          </DialogHeader>
          {recoveryCodes ? (
            <>
              <div className="grid grid-cols-2 gap-2 rounded-md border bg-muted/20 p-3 font-mono text-xs">
                {recoveryCodes.map((code) => <span key={code}>{code}</span>)}
              </div>
              <div className="flex items-center justify-between gap-2">
                <CopyButton value={recoveryCodes.join("\n")} />
                <Button type="button" onClick={() => { setRecoveryCodes(null); setMfaSetup(null); }}>
                  {t("profile.mfaClose")}
                </Button>
              </div>
            </>
          ) : mfaSetup ? (
            <>
              <div className="space-y-2">
                <Label>{t("profile.mfaSecret")}</Label>
                <div className="flex items-center gap-2">
                  <Input readOnly value={mfaSetup.secret} className="font-mono text-xs" />
                  <CopyButton value={mfaSetup.secret} />
                </div>
                <p className="break-all font-mono text-[10px] text-muted-foreground">{mfaSetup.otpauth_uri}</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="mfa-confirm-code">{t("profile.mfaCodeLabel")}</Label>
                <Input
                  id="mfa-confirm-code"
                  value={mfaCode}
                  onChange={(event) => setMfaCode(event.target.value)}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  placeholder="000000"
                  className="font-mono tracking-[0.25em]"
                />
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => { setMfaSetup(null); setMfaCode(""); }}>
                  {t("common.cancel")}
                </Button>
                <Button
                  type="button"
                  onClick={() => enableMfa.mutate()}
                  disabled={!mfaCode.trim() || enableMfa.isPending}
                >
                  {enableMfa.isPending ? <Spinner /> : <ShieldCheck />}
                  {t("profile.mfaConfirm")}
                </Button>
              </DialogFooter>
            </>
          ) : null}
        </DialogContent>
      </Dialog>

      <Dialog open={disableOpen} onOpenChange={(open) => { setDisableOpen(open); if (!open) { setDisablePassword(""); setDisableCode(""); setDisableError(null); } }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t("profile.mfaDisableTitle")}</DialogTitle>
            <DialogDescription>{t("profile.mfaDisableDescription")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="mfa-disable-password">{t("profile.mfaPassword")}</Label>
              <PasswordInput id="mfa-disable-password" value={disablePassword} onChange={(event) => setDisablePassword(event.target.value)} autoComplete="current-password" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mfa-disable-code">{t("profile.mfaCodeLabel")}</Label>
              <Input id="mfa-disable-code" value={disableCode} onChange={(event) => setDisableCode(event.target.value)} inputMode="numeric" autoComplete="one-time-code" />
            </div>
            {disableError ? <p className="text-xs text-destructive">{disableError}</p> : null}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDisableOpen(false)}>{t("common.cancel")}</Button>
            <Button type="button" variant="destructive" onClick={() => disableMfa.mutate()} disabled={!disablePassword || !disableCode.trim() || disableMfa.isPending}>
              {disableMfa.isPending ? <Spinner /> : null}
              {t("profile.mfaDisable")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
