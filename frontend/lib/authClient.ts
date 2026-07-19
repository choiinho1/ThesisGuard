import type { AuthUser, LoginInput, SignupInput, TokenResponse } from "@/types/schema";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const TOKEN_KEY = "thesisguard_access_token";
const AUTH_REQUEST_TIMEOUT_MS = 10_000;

async function fetchWithTimeout(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(
    () => controller.abort(),
    AUTH_REQUEST_TIMEOUT_MS,
  );

  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("서버 응답이 지연되고 있습니다. 잠시 후 다시 시도해 주세요.");
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
}

async function authRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const token = typeof window === "undefined" ? null : localStorage.getItem(TOKEN_KEY);
  const response = await fetchWithTimeout(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null) as
      | { detail?: string | Array<{ msg?: string }> }
      | null;
    const detail = payload?.detail;
    const message = typeof detail === "string"
      ? detail
      : Array.isArray(detail)
        ? detail.map((item) => item.msg).filter(Boolean).join(" ")
        : null;
    throw new Error(message || `인증 요청에 실패했습니다. (${response.status})`);
  }

  return response.json() as Promise<T>;
}

export function hasAccessToken(): boolean {
  return typeof window !== "undefined" && Boolean(localStorage.getItem(TOKEN_KEY));
}

export async function login(input: LoginInput): Promise<AuthUser> {
  const token = await authRequest<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
  localStorage.setItem(TOKEN_KEY, token.access_token);

  try {
    return await getCurrentUser();
  } catch (error) {
    localStorage.removeItem(TOKEN_KEY);
    throw error;
  }
}

export async function loginWithGoogle(idToken: string): Promise<AuthUser> {
  const token = await authRequest<TokenResponse>("/api/auth/google", {
    method: "POST",
    body: JSON.stringify({ id_token: idToken }),
  });
  localStorage.setItem(TOKEN_KEY, token.access_token);

  try {
    return await getCurrentUser();
  } catch (error) {
    localStorage.removeItem(TOKEN_KEY);
    throw error;
  }
}

export async function signup(input: SignupInput): Promise<AuthUser> {
  return authRequest<AuthUser>("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getCurrentUser(): Promise<AuthUser> {
  return authRequest<AuthUser>("/api/auth/me");
}

export function logout(): void {
  localStorage.removeItem(TOKEN_KEY);
}
