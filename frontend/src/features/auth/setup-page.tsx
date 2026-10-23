import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft, ArrowRight, Check, Monitor, Moon, ShieldCheck, Sun, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { AuthLayout } from "@/features/auth/auth-layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/shared/password-input";
import { Spinner } from "@/components/shared/loaders";
import { usePageTitle } from "@/hooks/use-app";
import { useAuth } from "@/lib/auth";
import { changeLanguage, currentLanguage } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import { setupSchema } from "@/lib/validation";
import { cn } from "@/lib/utils";
import type { Theme } from "@/types/api";

interface SetupValues {
  username: string;
  password: string;
  confirm_password: string;
  language: string;
  theme: Theme;
}

export function SetupPage() {
  const { t } = useTranslation();
  const { setup, meta } = useAuth();
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [selectedLanguage, setSelectedLanguage] = useState(currentLanguage());
  usePageTitle("auth.setupTitle");

  const form = useForm<SetupValues>({
    resolver: zodResolver(setupSchema(t)),
    defaultValues: {
      username: "",
      password: "",
      confirm_password: "",
      language: currentLanguage(),
      theme,
    },
  });

  const available = meta?.available_languages?.length ? meta.available_languages : ["es", "en"];
  const themes: { value: Theme; icon: typeof Sun }[] = [
    { value: "light", icon: Sun },
    { value: "dark", icon: Moon },
    { value: "system", icon: Monitor },
  ];

  const submit = form.handleSubmit(async (values) => {
    setServerError(null);
    setSubmitting(true);
    try {
      await setup({
        username: values.username,
        password: values.password,
        language: values.language,
        theme: values.theme,
      });
      toast.success(t("auth.setupDone"));
      navigate("/", { replace: true });
    } catch {
      setServerError(t("auth.setupError"));
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <AuthLayout
      eyebrow={t("auth.setupEyebrow")}
      title={t("auth.setupTitle")}
      description={t("auth.setupSubtitle")}
      heroTitle={t("auth.brandTitle")}
      heroDescription={t("auth.brandSubtitle")}
      points={[t("auth.brandPointInventory"), t("auth.setupPoint")]}
      footer={t("auth.setupFooter")}
    >
      <div className="mb-5 flex items-center gap-2">
        <div className="flex flex-1 items-center gap-1.5">
          {[0, 1].map((index) => (
            <div
              key={index}
              className={cn("h-1 flex-1 rounded-full transition-colors", index <= step ? "bg-primary" : "bg-muted")}
            />
          ))}
        </div>
        <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">
          {t("auth.stepOf", { current: step + 1, total: 2 })}
        </span>
      </div>

      {step === 0 ? (
        <div className="space-y-5">
          <div>
            <h3 className="text-sm font-semibold">{t("auth.preferencesStep")}</h3>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{t("auth.preferencesStepDescription")}</p>
          </div>
          <div className="space-y-2">
            <Label>{t("common.language")}</Label>
            <div className="grid grid-cols-2 gap-2">
              {available.map((language) => (
                <button
                  key={language}
                  type="button"
                  onClick={() => {
                    setSelectedLanguage(language);
                    form.setValue("language", language);
                    void changeLanguage(language);
                  }}
                  className={cn(
                    "flex items-center justify-between rounded-md border px-3 py-2.5 text-sm transition-colors",
                    selectedLanguage === language
                      ? "border-primary/40 bg-primary/[0.06] text-foreground"
                      : "bg-card text-muted-foreground hover:border-foreground/15",
                  )}
                >
                  {t(`languages.${language}`)}
                  {selectedLanguage === language ? <Check className="h-4 w-4 text-primary" /> : null}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            <Label>{t("common.theme")}</Label>
            <div className="grid grid-cols-3 gap-2">
              {themes.map(({ value, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => {
                    setTheme(value, { persist: true });
                    form.setValue("theme", value);
                  }}
                  className={cn(
                    "flex flex-col items-center gap-2 rounded-md border px-2 py-3 text-[11px] transition-colors",
                    form.watch("theme") === value
                      ? "border-primary/40 bg-primary/[0.06] text-foreground"
                      : "bg-card text-muted-foreground hover:border-foreground/15",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {t(`theme.${value}`)}
                </button>
              ))}
            </div>
          </div>
          <Button
            type="button"
            className="w-full justify-between"
            onClick={() => {
              form.setValue("theme", form.getValues("theme"));
              setStep(1);
            }}
          >
            {t("common.continue")}
            <ArrowRight />
          </Button>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <ShieldCheck className="h-4 w-4 text-primary" />
              {t("auth.accountStep")}
            </h3>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{t("auth.accountStepDescription")}</p>
          </div>
          {serverError ? (
            <div role="alert" className="flex items-start gap-2 rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive">
              <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {serverError}
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="setup-username">{t("auth.username")}</Label>
            <Input
              id="setup-username"
              autoComplete="username"
              autoFocus
              aria-invalid={Boolean(form.formState.errors.username)}
              {...form.register("username")}
            />
            {form.formState.errors.username ? (
              <p className="text-xs text-destructive">{form.formState.errors.username.message}</p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="setup-password">{t("auth.password")}</Label>
            <PasswordInput
              id="setup-password"
              autoComplete="new-password"
              aria-invalid={Boolean(form.formState.errors.password)}
              {...form.register("password")}
            />
            <p className="text-[11px] leading-relaxed text-muted-foreground">{t("auth.passwordHint")}</p>
            {form.formState.errors.password ? (
              <p className="text-xs text-destructive">{form.formState.errors.password.message}</p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="setup-confirm">{t("auth.confirmPassword")}</Label>
            <PasswordInput
              id="setup-confirm"
              autoComplete="new-password"
              aria-invalid={Boolean(form.formState.errors.confirm_password)}
              {...form.register("confirm_password")}
            />
            {form.formState.errors.confirm_password ? (
              <p className="text-xs text-destructive">{form.formState.errors.confirm_password.message}</p>
            ) : null}
          </div>
          <div className="flex gap-2 pt-1">
            <Button type="button" variant="outline" onClick={() => setStep(0)} disabled={submitting}>
              <ArrowLeft />
              {t("common.back")}
            </Button>
            <Button type="submit" className="flex-1 justify-between" disabled={submitting}>
              {submitting ? <Spinner /> : <ShieldCheck />}
              {submitting ? t("auth.creatingAdmin") : t("auth.createAdmin")}
              {!submitting ? <ArrowRight /> : null}
            </Button>
          </div>
        </form>
      )}
    </AuthLayout>
  );
}
