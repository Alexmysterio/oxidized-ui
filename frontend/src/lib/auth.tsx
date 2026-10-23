import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";

import { api, setCsrfToken } from "@/lib/api";
import { changeLanguage } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import type { Meta, MfaChallenge, SessionPayload, User } from "@/types/api";

interface AuthContextValue {
  meta: Meta | null;
  user: User | null;
  capabilities: string[];
  loading: boolean;
  setupRequired: boolean;
  login: (username: string, password: string) => Promise<MfaChallenge | null>;
  setup: (payload: { username: string; password: string; language: string; theme?: string }) => Promise<void>;
  logout: () => Promise<void>;
  applySession: (session: SessionPayload) => Promise<void>;
  updateUser: (user: User) => void;
  refresh: () => Promise<void>;
  can: (capability: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const { setTheme } = useTheme();
  const expiredNotice = useRef(false);

  const metaQuery = useQuery({
    queryKey: ["meta"],
    queryFn: api.meta,
    staleTime: 60_000,
    retry: 1,
  });

  const setupRequired = metaQuery.data?.setup_required ?? false;

  const sessionQuery = useQuery({
    queryKey: ["session"],
    queryFn: api.session,
    enabled: !metaQuery.isLoading && !setupRequired,
    retry: false,
    staleTime: 30_000,
  });

  const applySession = useCallback(
    async (session: SessionPayload) => {
      setCsrfToken(session.csrf_token);
      queryClient.setQueryData(["session"], session);
      await changeLanguage(session.user.language, { persist: true });
      setTheme(session.user.theme, { persist: true });
    },
    [queryClient, setTheme],
  );

  useEffect(() => {
    const unauthorized = () => {
      queryClient.setQueryData(["session"], null);
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "meta" });
      if (!expiredNotice.current) {
        expiredNotice.current = true;
        toast.error(t("auth.sessionExpired"));
      }
    };
    window.addEventListener(api.unauthorizedEvent, unauthorized);
    return () => window.removeEventListener(api.unauthorizedEvent, unauthorized);
  }, [queryClient, t]);

  useEffect(() => {
    const session = sessionQuery.data;
    if (!session) return;
    expiredNotice.current = false;
    setCsrfToken(session.csrf_token);
    void changeLanguage(session.user.language, { persist: true });
    setTheme(session.user.theme, { persist: true });
  }, [sessionQuery.data, setTheme]);

  useEffect(() => {
    if (sessionQuery.error && !setupRequired) {
      setCsrfToken(null);
    }
  }, [sessionQuery.error, setupRequired]);

  const login = useCallback(
    async (username: string, password: string): Promise<MfaChallenge | null> => {
      const result = await api.login(username, password);
      if ("mfa_required" in result) return result;
      await applySession(result);
      return null;
    },
    [applySession],
  );

  const setup = useCallback(
    async (payload: { username: string; password: string; language: string; theme?: string }) => {
      const session = await api.setup(payload);
      await applySession(session);
      await queryClient.invalidateQueries({ queryKey: ["meta"] });
    },
    [applySession, queryClient],
  );

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      // The local session is cleared even if the server already expired it.
    } finally {
      setCsrfToken(null);
      queryClient.setQueryData(["session"], null);
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "meta" });
    }
  }, [queryClient]);

  const updateUser = useCallback(
    (user: User) => {
      queryClient.setQueryData<SessionPayload | null>(["session"], (current) =>
        current ? { ...current, user } : current,
      );
    },
    [queryClient],
  );

  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["session"] });
  }, [queryClient]);

  const user = sessionQuery.data?.user ?? null;
  const capabilities = sessionQuery.data?.capabilities ?? [];

  const value = useMemo<AuthContextValue>(
    () => ({
      meta: metaQuery.data ?? null,
      user,
      capabilities,
      loading: metaQuery.isLoading || (!setupRequired && sessionQuery.isLoading),
      setupRequired,
      login,
      setup,
      logout,
      applySession,
      updateUser,
      refresh,
      can: (capability) => capabilities.includes(capability),
    }),
    [
      metaQuery.data,
      metaQuery.isLoading,
      setupRequired,
      sessionQuery.isLoading,
      user,
      capabilities,
      login,
      setup,
      logout,
      applySession,
      updateUser,
      refresh,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
