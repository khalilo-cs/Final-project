import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { ApiError, get, loadTokens, post, saveTokens, type User } from "./api";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  register: (data: Record<string, string>) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    try {
      setUser(loadTokens() ? await get<User>("auth", "/api/v1/auth/me") : null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) saveTokens(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMe();
  }, [loadMe]);

  const login = async (username: string, password: string) => {
    saveTokens(await post("auth", "/api/v1/auth/login", { username, password }));
    await loadMe();
  };

  const register = async (data: Record<string, string>) => {
    await post("auth", "/api/v1/auth/register", data);
    await login(data.username, data.password);
  };

  const logout = async () => {
    const tokens = loadTokens();
    if (tokens) {
      await post("auth", "/api/v1/auth/logout", { refresh_token: tokens.refresh_token }).catch(
        () => undefined,
      );
    }
    saveTokens(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth outside AuthProvider");
  return context;
}
