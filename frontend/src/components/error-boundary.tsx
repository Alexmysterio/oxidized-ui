import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import i18n from "@/lib/i18n";

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("UI boundary", error, info.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="grid min-h-screen place-items-center bg-background p-6">
        <div className="w-full max-w-md rounded-xl border bg-card p-6 text-center shadow-lift">
          <p className="eyebrow mb-2">{i18n.t("errors.title")}</p>
          <h1 className="text-xl font-semibold tracking-tight">{i18n.t("common.unexpectedError")}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{i18n.t("common.loadingErrorDescription")}</p>
          <Button className="mt-5" onClick={() => window.location.reload()}>
            {i18n.t("common.tryAgain")}
          </Button>
        </div>
      </div>
    );
  }
}
