import { Compass, ShieldX } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { usePageTitle } from "@/hooks/use-app";

export function NotFoundPage() {
  const { t } = useTranslation();
  usePageTitle("notFound.title");
  return (
    <div className="app-grid relative flex min-h-[70vh] items-center justify-center rounded-xl border bg-card/30 p-6">
      <div className="relative text-center">
        <p className="font-mono text-[9px] uppercase tracking-[0.28em] text-muted-foreground">{t("notFound.eyebrow")}</p>
        <EmptyState
          icon={Compass}
          title={t("notFound.title")}
          description={t("notFound.description")}
          action={<Button asChild><Link to="/">{t("notFound.goDashboard")}</Link></Button>}
          className="border-0 bg-transparent shadow-none"
        />
      </div>
    </div>
  );
}

export function ForbiddenPage() {
  const { t } = useTranslation();
  usePageTitle("forbidden.title");
  return (
    <div className="app-grid relative flex min-h-[70vh] items-center justify-center rounded-xl border bg-card/30 p-6">
      <div className="relative text-center">
        <p className="font-mono text-[9px] uppercase tracking-[0.28em] text-muted-foreground">{t("forbidden.eyebrow")}</p>
        <EmptyState
          icon={ShieldX}
          title={t("forbidden.title")}
          description={t("forbidden.description")}
          action={<Button asChild><Link to="/">{t("forbidden.goDashboard")}</Link></Button>}
          className="border-0 bg-transparent shadow-none"
        />
      </div>
    </div>
  );
}
