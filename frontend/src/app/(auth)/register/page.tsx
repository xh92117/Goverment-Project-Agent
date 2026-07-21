"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowRightIcon, CheckIcon, EyeIcon, EyeOffIcon, LockKeyholeIcon, MailIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { registerLocal } from "@/features/auth/api";
import { AUTH_STATE_QUERY_KEY, AuthGate } from "@/features/auth/auth-gate";
import { AuthPageShell } from "@/features/auth/auth-page-shell";
import { authErrorMessage, validatePasswordConfirmation } from "@/features/auth/form-validation";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/form";

export default function RegisterPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const validationError = validatePasswordConfirmation(password, confirmPassword);
    if (validationError) {
      setError(validationError);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await registerLocal({ email: email.trim(), password });
      await queryClient.invalidateQueries({ queryKey: AUTH_STATE_QUERY_KEY });
      router.replace("/workspace/projects");
    } catch (caught) {
      setError(authErrorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  const hasLength = password.length >= 8;
  const hasVariety = /[A-Za-z]/.test(password) && /\d/.test(password);

  return (
    <AuthGate surface="register">
      <AuthPageShell
        eyebrow="加入工作空间"
        title="创建个人账号"
        description="注册后将自动建立独立的数据与记忆空间。"
      >
        <form className="auth-form" onSubmit={(event) => void submit(event)}>
          <label className="auth-field" htmlFor="register-email">
            <span>邮箱</span>
            <span className="auth-input-wrap">
              <MailIcon aria-hidden="true" />
              <Input
                id="register-email"
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

          <label className="auth-field" htmlFor="register-password">
            <span>设置密码</span>
            <span className="auth-input-wrap">
              <LockKeyholeIcon aria-hidden="true" />
              <Input
                id="register-password"
                name="password"
                type={showPassword ? "text" : "password"}
                value={password}
                autoComplete="new-password"
                placeholder="至少 8 位，建议包含字母与数字"
                required
                minLength={8}
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

          <label className="auth-field" htmlFor="register-confirm-password">
            <span>确认密码</span>
            <span className="auth-input-wrap">
              <LockKeyholeIcon aria-hidden="true" />
              <Input
                id="register-confirm-password"
                name="confirm-password"
                type={showPassword ? "text" : "password"}
                value={confirmPassword}
                autoComplete="new-password"
                placeholder="再次输入密码"
                required
                onChange={(event) => setConfirmPassword(event.target.value)}
              />
            </span>
          </label>

          <div className="auth-password-rules" aria-label="密码要求">
            <span className={hasLength ? "met" : ""}><CheckIcon />至少 8 位</span>
            <span className={hasVariety ? "met" : ""}><CheckIcon />建议包含字母与数字</span>
          </div>

          {error ? <div className="auth-error" role="alert">{error}</div> : null}

          <Button className="auth-submit" type="submit" variant="primary" loading={loading}>
            创建账号
            {!loading ? <ArrowRightIcon aria-hidden="true" /> : null}
          </Button>
        </form>

        <div className="auth-panel-foot">
          <span>已有账号？</span>
          <Link href="/login">返回登录</Link>
        </div>
      </AuthPageShell>
    </AuthGate>
  );
}
