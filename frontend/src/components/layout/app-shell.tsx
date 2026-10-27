import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { SearchDialog } from "@/components/layout/search-dialog";
import { Sidebar, SidebarContent } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { cn } from "@/lib/utils";

const SIDEBAR_KEY = "oxidized-ui-sidebar-collapsed";

function releaseBodyLocks() {
  if (document.querySelector('[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]')) {
    return;
  }
  if (document.body.style.pointerEvents === "none") {
    document.body.style.pointerEvents = "";
  }
  if (document.body.style.overflow === "hidden" && !document.body.hasAttribute("data-scroll-locked")) {
    document.body.style.overflow = "";
  }
  document.body.removeAttribute("data-scroll-locked");
}

export function AppShell() {
  const { t } = useTranslation();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_KEY) === "1";
    } catch {
      return false;
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
    window.scrollTo({ top: 0, behavior: "auto" });
    const frame = requestAnimationFrame(releaseBodyLocks);
    return () => cancelAnimationFrame(frame);
  }, [location.pathname]);

  useEffect(() => {
    const observer = new MutationObserver(releaseBodyLocks);
    observer.observe(document.body, { attributes: true, attributeFilter: ["style", "class", "data-scroll-locked"] });
    const timer = window.setInterval(releaseBodyLocks, 1000);
    window.addEventListener("popstate", releaseBodyLocks);
    return () => {
      observer.disconnect();
      window.clearInterval(timer);
      window.removeEventListener("popstate", releaseBodyLocks);
    };
  }, []);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  const toggleCollapsed = () => {
    setCollapsed((value) => {
      const next = !value;
      try {
        localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0");
      } catch {
        // Ignore.
      }
      return next;
    });
  };

  return (
    <div className="min-h-screen bg-background">
      <a
        href="#main-content"
        className="sr-only z-[100] rounded-md bg-card px-3 py-2 text-sm shadow-lift focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
      >
        {t("nav.skipToContent")}
      </a>
      <Sidebar collapsed={collapsed} onToggle={toggleCollapsed} />
      {mobileOpen ? (
        <div className="fixed inset-0 z-[70] lg:hidden">
          <button
            type="button"
            aria-label={t("nav.closeMenu")}
            className="absolute inset-0 h-full w-full bg-slate-950/55 backdrop-blur-[2px]"
            onClick={() => setMobileOpen(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t("nav.mainNavigation")}
            className="absolute inset-y-0 left-0 w-[280px] border-r border-sidebar-border bg-sidebar shadow-lift"
          >
            <SidebarContent mobile onNavigate={() => setMobileOpen(false)} onClose={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className={cn("min-h-screen transition-[padding] duration-200", collapsed ? "lg:pl-20" : "lg:pl-[268px]")}>
        <Topbar onOpenMenu={() => setMobileOpen(true)} onOpenSearch={() => setSearchOpen(true)} />
        <main id="main-content" className="relative min-h-[calc(100vh-4rem)] overflow-hidden">
          <div className="app-grid pointer-events-none absolute inset-x-0 top-0 h-[26rem] opacity-70" />
          <div className="relative mx-auto w-full max-w-[1480px] px-4 py-6 sm:px-6 sm:py-8 xl:px-8">
            <Outlet />
          </div>
        </main>
      </div>
      <SearchDialog open={searchOpen} onOpenChange={setSearchOpen} />
    </div>
  );
}
