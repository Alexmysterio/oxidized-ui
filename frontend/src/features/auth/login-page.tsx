import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowRight, LockKeyhole, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { AuthLayout } from "@/features/auth/auth-layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/shared/password-input";
import { Spinner } from "@/components/shared/loaders";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { usePageTitle } from "@/hooks/use-app";
import { loginSchema } from "@/lib/validation";
import type { MfaChallenge } from "@/types/api";

interface LoginValues {
  username: string;
  password: string;
}

export function LoginPage() {
  const { t } = useTranslation();
  const { login, applySession, meta } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [challenge, setChallenge] = useState<MfaChallenge | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  usePageTitle("auth.loginTitle");

  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema(t)),
    defaultValues: { username: "", password: "" },
  });

  const onSubmit = form.handleSubmit(async (values) => {
    setServerError(null);
    setSubmitting(true);
    try {
      if (challenge) {
        if (!mfaCode.trim()) {
          setServerError(t("auth.mfaCodeRequired"));
          return;
        }
        const session = await api.loginMfa(challenge.challenge_token, mfaCode.trim());
        await applySession(session);
      } else {
        const next = await login(values.username, values.password);
        if (next) {
          setChallenge(next);
          setMfaCode("");
          return;
        }
      }
      toast.success(t("auth.welcomeBack", { username: values.username }));
      const target = (location.state as { from?: string } | null)?.from ?? "/";
      navigate(target, { replace: true });
    } catch (error) {
      if (error instanceof ApiError && error.code === "auth.invalid_mfa_code") {
        setServerError(t("auth.invalidMfaCode"));
      } else if (error instanceof ApiError && error.code === "auth.mfa_challenge_expired") {
        setChallenge(null);
        setServerError(t("auth.mfaExpired"));
      } else if (error instanceof ApiError && error.code === "auth.too_many_attempts") {
        setServerError(t("auth.loginRateLimited"));
      } else {
        setServerError(t("auth.loginError"));
      }
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <AuthLayout
      eyebrow={t("auth.loginEyebrow")}
      title={t("auth.loginTitle")}
      description={t("auth.loginSubtitle")}
      heroTitle={t("auth.loginHeroTitle")}
      heroDescription={t("auth.loginHeroDescription")}
      points={[t("auth.brandPointInventory"), t("auth.brandPointHistory"), t("auth.brandPointLive")]}
      footer={t("auth.noAccount")}
    >
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        <div className="flex items-center gap-2 rounded-md border border-border/70 bg-muted/40 px-2.5 py-2 text-[11px] text-muted-foreground">
          <LockKeyhole className="h-3.5 w-3.5 text-primary" />
          {t("auth.secureConnection")}
        </div>
        {serverError ? (
          <div role="alert" className="flex items-start gap-2 rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs leading-relaxed text-destructive">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {serverError}
          </div>
        ) : null}
        <div className="space-y-2">
          <Label htmlFor="username">{t("auth.username")}</Label>
          <Input
            id="username"
            autoComplete="username"
            autoFocus
            placeholder={t("auth.usernamePlaceholder")}
            aria-invalid={Boolean(form.formState.errors.username)}
            {...form.register("username")}
            disabled={Boolean(challenge)}
          />
          {form.formState.errors.username ? (
            <p className="text-xs text-destructive">{form.formState.errors.username.message}</p>
          ) : null}
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">{t("auth.password")}</Label>
          <PasswordInput
            id="password"
            autoComplete="current-password"
            placeholder={t("auth.passwordPlaceholder")}
            aria-invalid={Boolean(form.formState.errors.password)}
            {...form.register("password")}
            disabled={Boolean(challenge)}
          />
          {form.formState.errors.password ? (
            <p className="text-xs text-destructive">{form.formState.errors.password.message}</p>
          ) : null}
        </div>
        {challenge ? (
          <div className="space-y-2 rounded-md border border-primary/20 bg-primary/[0.04] p-3">
            <p className="text-xs leading-relaxed text-muted-foreground">{t("auth.mfaPrompt")}</p>
            <Label htmlFor="mfa-code">{t("auth.mfaCode")}</Label>
            <Input
              id="mfa-code"
              value={mfaCode}
              onChange={(event) => setMfaCode(event.target.value)}
              autoFocus
              autoComplete="one-time-code"
              inputMode="numeric"
              placeholder="000000"
              className="font-mono tracking-[0.25em]"
            />
            <button
              type="button"
              className="text-left text-[11px] text-muted-foreground underline-offset-2 hover:underline"
              onClick={() => {
                setChallenge(null);
                setMfaCode("");
                setServerError(null);
              }}
            >
              {t("auth.mfaBack")}
            </button>
          </div>
        ) : null}
        <Button
          type="submit"
          className="h-10 w-full justify-between"
          disabled={submitting || (Boolean(challenge) && !mfaCode.trim())}
        >
          <span className="inline-flex items-center gap-2">
            {submitting ? <Spinner /> : <LockKeyhole />}
            {submitting ? t("auth.signingIn") : challenge ? t("auth.verifyCode") : t("auth.signIn")}
          </span>
          {!submitting ? <ArrowRight /> : null}
        </Button>
        {meta?.oidc_enabled ? (
          <Button type="button" variant="outline" className="h-10 w-full" onClick={() => { window.location.href = "/api/auth/oidc/login"; }}>
            <LockKeyhole />
            {t("auth.oidcLogin")}
          </Button>
        ) : null}
      </form>
    </AuthLayout>
  );
}
