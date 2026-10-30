"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "./api";
import type { Session, Workspace } from "./types";

interface AuthContextValue {
  session: Session | null;
  loading: boolean;
  workspaces: Workspace[];
  workspace: Workspace | null;
  setWorkspaceId: (id: string) => void;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: { email: string; password: string; full_name: string; organization_name?: string }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);
const WORKSPACE_KEY = "abi.workspace";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [workspaceId, setWorkspaceIdState] = useState<string | null>(null);
  const router = useRouter();

  const refresh = useCallback(async () => {
    try {
      const next = await api.get<Session>("/auth/me");
      setSession(next);
      setWorkspaceIdState((current) => {
        const stored = typeof window !== "undefined" ? window.localStorage.getItem(WORKSPACE_KEY) : null;
        const candidate = current || stored;
        const valid = next.workspaces.find((w) => w.id === candidate);
        return valid?.id || next.workspaces[0]?.id || null;
      });
    } catch {
      setSession(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const handler = () => {
      setSession(null);
      setLoading(false);
    };
    window.addEventListener("abi:unauthorized", handler);
    return () => window.removeEventListener("abi:unauthorized", handler);
  }, []);

  const setWorkspaceId = useCallback((id: string) => {
    setWorkspaceIdState(id);
    try {
      window.localStorage.setItem(WORKSPACE_KEY, id);
    } catch {
      /* ignore */
    }
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const next = await api.post<Session>("/auth/login", { email, password });
      setSession(next);
      setWorkspaceId(next.workspaces[0]?.id ?? "");
    },
    [setWorkspaceId],
  );

  const register = useCallback(
    async (payload: { email: string; password: string; full_name: string; organization_name?: string }) => {
      const next = await api.post<Session>("/auth/register", payload);
      setSession(next);
      setWorkspaceId(next.workspaces[0]?.id ?? "");
    },
    [setWorkspaceId],
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } finally {
      setSession(null);
      router.push("/login");
    }
  }, [router]);

  const workspace = useMemo(
    () => session?.workspaces.find((w) => w.id === workspaceId) ?? session?.workspaces[0] ?? null,
    [session, workspaceId],
  );

  const value = useMemo(
    () => ({
      session,
      loading,
      workspaces: session?.workspaces ?? [],
      workspace,
      setWorkspaceId,
      refresh,
      login,
      register,
      logout,
    }),
    [session, loading, workspace, setWorkspaceId, refresh, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
