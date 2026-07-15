"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { loginLocal } from "@/features/auth/api";
import { Button } from "@/shared/ui/button";
import { Field, Input } from "@/shared/ui/form";

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const [email, setEmail] = useState("admin@govdecl.cn");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await loginLocal(email, password);
      router.replace(search.get("next") ?? "/workspace/projects");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form className="card stack" style={{ width: 380 }} onSubmit={(event) => void submit(event)}>
      <div>
        <div className="brand-name">智策登录</div>
        <p className="muted">使用本地管理员账号进入申报工作台。</p>
      </div>
      <Field label="邮箱">
        <Input value={email} onChange={(event) => setEmail(event.target.value)} />
      </Field>
      <Field label="密码">
        <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
      </Field>
      {error && <div className="error-state">{error}</div>}
      <Button variant="primary" loading={loading}>登录</Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="app-shell" style={{ display: "grid", placeItems: "center" }}>
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
