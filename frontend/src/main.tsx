import { QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "@/App";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/lib/auth";
import { initializeI18n, loadInitialMeta } from "@/lib/i18n";
import i18n from "@/lib/i18n";
import { queryClient } from "@/lib/query-client";
import { ThemeProvider } from "@/lib/theme";

import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./index.css";

async function bootstrap() {
  const meta = await loadInitialMeta();
  await initializeI18n(meta);
  document.title = i18n.t("app.name");
  const container = document.getElementById("root");
  if (!container) throw new Error("Root element not found");
  createRoot(container).render(
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <TooltipProvider delayDuration={180}>
            <BrowserRouter>
              <App />
            </BrowserRouter>
          </TooltipProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

void bootstrap();
