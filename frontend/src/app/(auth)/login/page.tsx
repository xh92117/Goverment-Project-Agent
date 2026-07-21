"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowRightIcon, EyeIcon, EyeOffIcon, LockKeyholeIcon, MailIcon } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { loginLocal } from "@/features/auth/api";
import { AUTH_STATE_QUERY_KEY, AuthGate } from "@/features/auth/auth-gate";
import { AuthPageShell } from "@/features/auth/auth-page-shell";
import { authErrorMessage } from "@/features/auth/form-validation";
import { safeWorkspaceDestination } from "@/features/auth/route-policy";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/form";

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await loginLocal(email.trim(), password);
      await queryClient.invalidateQueries({ queryKey: AUTH_STATE_QUERY_KEY });
      router.replace(safeWorkspaceDestination(search.get("next")));
    } catch (caught) {
      setError(authErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthGate surface="login">
      <AuthPageShell
        eyebrow="欢迎回来"
        title="登录工作台"
        description="使用你的账号继续项目申报工作。"
      >
        <form className="auth-form" onSubmit={(event) => void submit(event)}>
          <label className="auth-field" htmlFor="login-email">
            <span>邮箱</span>
            <span className="auth-input-wrap">
              <MailIcon aria-hidden="true" />
              <Input
                id="login-email"
                name="email"
                type="email"
                value={email}
                autoComplete="email"
                placeholder="name@example.com"
                required
                autoFocus
                onChange={(event) => setEmail(event.target.value)}
              />
            </span>
          </label>

          <label className="auth-field" htmlFor="login-password">
            <span>密码</span>
            <span className="auth-input-wrap">
              <LockKeyholeIcon aria-hidden="true" />
              <Input
                id="login-password"
                name="password"
                type={showPassword ? "text" : "password"}
                value={password}
                autoComplete="current-password"
                placeholder="输入登录密码"
                required
                onChange={(event) => setPassword(event.target.value)}
              />
              <button
                className="auth-password-toggle"
                type="button"
                aria-label={showPassword ? "隐藏密码" : "显示密码"}
                onClick={() => setShowPassword((visible) => !visible)}
              >
                {showPassword ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </span>
          </label>

          {error ? <div className="auth-error" role="alert">{error}</div> : null}

          <Button className="auth-submit" type="submit" variant="primary" loading={loading}>
            登录
            {!loading ? <ArrowRightIcon aria-hidden="true" /> : null}
          </Button>
        </form>

        <div className="auth-panel-foot">
          <span>还没有账号？</span>
          <Link href="/register">创建个人账号</Link>
        </div>
      </AuthPageShell>
    </AuthGate>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="auth-status-screen">正在打开登录页…</div>}>
      <LoginForm />
    </Suspense>
  );
}
