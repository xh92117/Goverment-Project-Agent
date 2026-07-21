"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowRightIcon, CheckIcon, EyeIcon, EyeOffIcon, LockKeyholeIcon, MailIcon, ShieldCheckIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { initializeAdmin } from "@/features/auth/api";
import { AUTH_STATE_QUERY_KEY, AuthGate } from "@/features/auth/auth-gate";
import { AuthPageShell } from "@/features/auth/auth-page-shell";
import { authErrorMessage, validatePasswordConfirmation } from "@/features/auth/form-validation";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/form";

export default function SetupPage() {
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
      await initializeAdmin({ email: email.trim(), password });
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
    <AuthGate surface="setup">
      <AuthPageShell
        admin
        eyebrow="首次部署 · 管理员设置"
        title="创建系统管理员"
        description="此账号拥有系统配置权限，创建后即可进入工作台。"
      >
        <div className="auth-admin-notice">
          <ShieldCheckIcon aria-hidden="true" />
          <span><strong>仅首次部署可执行</strong>系统只允许通过此页面创建第一位管理员。</span>
        </div>

        <form className="auth-form" onSubmit={(event) => void submit(event)}>
          <label className="auth-field" htmlFor="setup-email">
            <span>管理员邮箱</span>
            <span className="auth-input-wrap">
              <MailIcon aria-hidden="true" />
              <Input
                id="setup-email"
                name="email"
                type="email"
                value={email}
                autoComplete="email"
                placeholder="admin@example.com"
                required
                autoFocus
                onChange={(event) => setEmail(event.target.value)}
              />
            </span>
          </label>

          <label className="auth-field" htmlFor="setup-password">
            <span>管理员密码</span>
            <span className="auth-input-wrap">
              <LockKeyholeIcon aria-hidden="true" />
              <Input
                id="setup-password"
                name="password"
                type={showPassword ? "text" : "password"}
                value={password}
                autoComplete="new-password"
                placeholder="设置管理员密码"
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

          <label className="auth-field" htmlFor="setup-confirm-password">
            <span>确认管理员密码</span>
            <span className="auth-input-wrap">
              <LockKeyholeIcon aria-hidden="true" />
              <Input
                id="setup-confirm-password"
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
            创建管理员并进入系统
            {!loading ? <ArrowRightIcon aria-hidden="true" /> : null}
          </Button>
        </form>
      </AuthPageShell>
    </AuthGate>
  );
}
