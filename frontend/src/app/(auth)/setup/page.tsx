"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { initializeAdmin } from "@/features/auth/api";
import { Button } from "@/shared/ui/button";
import { Field, Input } from "@/shared/ui/form";

export default function SetupPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await initializeAdmin({ email, password });
      router.replace("/workspace/projects");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell" style={{ display: "grid", placeItems: "center" }}>
      <form className="card stack" style={{ width: 420 }} onSubmit={(event) => void submit(event)}>
        <div>
          <div className="brand-name">初始化智策</div>
          <p className="muted">创建第一个本地管理员账号（邮箱 + 密码，密码至少 8 位且含字母与数字）。</p>
        </div>
        <Field label="邮箱">
          <Input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="admin@govdecl.cn" />
        </Field>
        <Field label="密码">
          <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="至少 8 位，含字母与数字" />
        </Field>
        {error && <div className="error-state">{error}</div>}
        <Button variant="primary" loading={loading}>完成初始化</Button>
      </form>
    </div>
  );
}
