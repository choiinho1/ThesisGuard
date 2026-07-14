"use client";

import Script from "next/script";
import { FormEvent, useEffect, useRef, useState } from "react";
import { Dashboard } from "@/components/Dashboard";
import {
  getCurrentUser,
  hasAccessToken,
  login,
  loginWithGoogle,
  logout,
  signup,
} from "@/lib/authClient";
import type { AuthUser } from "@/types/schema";

type AuthMode = "login" | "signup";

interface GoogleCredentialResponse {
  credential: string;
}

interface GoogleAccountsApi {
  initialize: (options: {
    client_id: string;
    callback: (response: GoogleCredentialResponse) => void;
  }) => void;
  renderButton: (
    parent: HTMLElement,
    options: {
      locale: string;
      shape: "rectangular";
      size: "large";
      text: "continue_with";
      theme: "outline";
      type: "standard";
      width: number;
    },
  ) => void;
}

declare global {
  interface Window {
    google?: { accounts: { id: GoogleAccountsApi } };
  }
}

interface GoogleSignInButtonProps {
  disabled: boolean;
  onCredential: (credential: string) => void;
  onUnavailable: () => void;
}

function GoogleSignInButton({ disabled, onCredential, onUnavailable }: GoogleSignInButtonProps) {
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
  const buttonRef = useRef<HTMLDivElement>(null);
  const credentialHandlerRef = useRef(onCredential);
  const [scriptReady, setScriptReady] = useState(false);

  useEffect(() => {
    credentialHandlerRef.current = onCredential;
  }, [onCredential]);

  useEffect(() => {
    if (!clientId || !scriptReady || !buttonRef.current || !window.google) return;

    const button = buttonRef.current;
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: (response) => credentialHandlerRef.current(response.credential),
    });
    button.replaceChildren();
    window.google.accounts.id.renderButton(button, {
      locale: "ko",
      shape: "rectangular",
      size: "large",
      text: "continue_with",
      theme: "outline",
      type: "standard",
      width: Math.min(button.clientWidth || 400, 400),
    });
  }, [clientId, scriptReady]);

  return (
    <>
      {clientId && (
        <Script
          onLoad={() => setScriptReady(true)}
          src="https://accounts.google.com/gsi/client?hl=ko"
          strategy="afterInteractive"
        />
      )}
      {clientId ? (
        <div aria-disabled={disabled} className="google-button-slot" ref={buttonRef} />
      ) : (
        <button className="google-button-fallback" disabled={disabled} onClick={onUnavailable} type="button">
          <span className="google-g" aria-hidden="true">G</span>
          Google로 계속하기
        </button>
      )}
    </>
  );
}

interface AuthScreenProps {
  onAuthenticated: (user: AuthUser) => void;
  onDemo: () => void;
}

function AuthScreen({ onAuthenticated, onDemo }: AuthScreenProps) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const changeMode = (nextMode: AuthMode) => {
    setMode(nextMode);
    setError(null);
  };

  const handleGoogleCredential = async (credential: string) => {
    setSubmitting(true);
    setError(null);
    try {
      onAuthenticated(await loginWithGoogle(credential));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Google 로그인을 처리하지 못했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);

    try {
      if (mode === "signup") {
        await signup({ email, password, ...(name.trim() ? { name: name.trim() } : {}) });
      }
      onAuthenticated(await login({ email, password }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "인증 요청을 처리하지 못했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="auth-shell">
      <section className="auth-story" aria-labelledby="auth-title">
        <a className="auth-brand" href="#auth-form" aria-label="ThesisGuard 로그인으로 이동">
          <span className="auth-brand-mark">TG</span>
          <span>THESISGUARD</span>
        </a>
        <div className="auth-story-copy">
          <p className="eyebrow">EVIDENCE-LED PORTFOLIO INTELLIGENCE</p>
          <h1 id="auth-title">투자 판단의 근거를<br />차분하게 관리하세요.</h1>
          <p>
            처음 세운 투자 가설과 달라진 근거를 한곳에서 확인하고,
            포트폴리오의 변화를 일관된 기준으로 살펴봅니다.
          </p>
        </div>
        <div className="auth-proof" aria-label="ThesisGuard 핵심 기능">
          <div><strong>01</strong><span>투자 논리 구조화</span></div>
          <div><strong>02</strong><span>근거 변화 추적</span></div>
          <div><strong>03</strong><span>설명 가능한 판단</span></div>
        </div>
      </section>

      <section className="auth-panel" id="auth-form">
        <div className="auth-card">
          <div className="auth-card-heading">
            <p className="kicker">SECURE ACCESS</p>
            <h2>{mode === "login" ? "로그인" : "계정 만들기"}</h2>
            <p>
              {mode === "login"
                ? "저장한 포트폴리오와 투자 논리를 이어서 확인하세요."
                : "계정을 만들고 첫 번째 투자 논리를 기록해 보세요."}
            </p>
          </div>

          <GoogleSignInButton
            disabled={submitting}
            onCredential={(credential) => { void handleGoogleCredential(credential); }}
            onUnavailable={() => setError("Google Client ID를 설정하면 Google 가입을 사용할 수 있습니다.")}
          />

          <div className="auth-divider"><span>또는 이메일로 계속</span></div>

          <div className="auth-tabs" role="tablist" aria-label="인증 방식">
            <button aria-selected={mode === "login"} className={mode === "login" ? "is-active" : ""} onClick={() => changeMode("login")} role="tab" type="button">로그인</button>
            <button aria-selected={mode === "signup"} className={mode === "signup" ? "is-active" : ""} onClick={() => changeMode("signup")} role="tab" type="button">회원가입</button>
          </div>

          <form className="auth-form" onSubmit={handleSubmit}>
            {mode === "signup" && (
              <label>
                <span>이름 <small>선택</small></span>
                <input autoComplete="name" onChange={(event) => setName(event.target.value)} placeholder="이름을 입력하세요" type="text" value={name} />
              </label>
            )}
            <label>
              <span>이메일</span>
              <input autoComplete="email" onChange={(event) => setEmail(event.target.value)} placeholder="name@example.com" required type="email" value={email} />
            </label>
            <label>
              <span>비밀번호 {mode === "signup" && <small>8자 이상</small>}</span>
              <span className="password-field">
                <input autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "signup" ? 8 : undefined} onChange={(event) => setPassword(event.target.value)} placeholder="비밀번호를 입력하세요" required type={showPassword ? "text" : "password"} value={password} />
                <button aria-label={showPassword ? "비밀번호 숨기기" : "비밀번호 보기"} onClick={() => setShowPassword((current) => !current)} type="button">{showPassword ? "숨김" : "보기"}</button>
              </span>
            </label>

            {error && <div className="auth-error" role="alert">{error}</div>}

            <button className="auth-submit" disabled={submitting} type="submit">
              <span>{submitting ? "확인하는 중..." : mode === "login" ? "로그인" : "계정 만들기"}</span>
              <span aria-hidden="true">→</span>
            </button>
            <button className="demo-button" disabled={submitting} onClick={onDemo} type="button">
              가입 없이 데모 화면 보기
            </button>
          </form>
        </div>
        <p className="auth-disclaimer">JWT 기반 보안 연결 · 투자 자문이 아닌 의사결정 지원 서비스입니다.</p>
      </section>
    </main>
  );
}

export function AuthGate() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const restoreSession = async () => {
      if (new URLSearchParams(window.location.search).get("demo") === "1") {
        setUser({
          id: "demo-user",
          email: "demo@thesisguard.local",
          name: "Demo",
          created_at: new Date(0).toISOString(),
        });
        setChecking(false);
        return;
      }

      if (!hasAccessToken()) {
        setChecking(false);
        return;
      }

      try {
        setUser(await getCurrentUser());
      } catch {
        logout();
      } finally {
        setChecking(false);
      }
    };

    void restoreSession();
  }, []);

  if (checking) return <main className="loading-screen">보안 세션을 확인하는 중...</main>;
  if (!user) {
    return (
      <AuthScreen
        onAuthenticated={setUser}
        onDemo={() => setUser({
          id: "demo-user",
          email: "demo@thesisguard.local",
          name: "Demo",
          created_at: new Date(0).toISOString(),
        })}
      />
    );
  }

  return (
    <>
      <div className="auth-session-bar">
        <span>{user.name || user.email}</span>
        <button onClick={() => { logout(); setUser(null); }} type="button">로그아웃</button>
      </div>
      <Dashboard />
    </>
  );
}
