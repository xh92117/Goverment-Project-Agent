export function validatePasswordConfirmation(password: string, confirmation: string) {
  if (password.length < 8) return "密码至少需要 8 位";
  if (password !== confirmation) return "两次输入的密码不一致";
  return null;
}

export function authErrorMessage(error: unknown) {
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();

  if (normalized.includes("incorrect email or password")) return "邮箱或密码不正确";
  if (normalized.includes("too many login attempts")) return "登录尝试过多，请稍后再试";
  if (normalized.includes("email already registered")) return "该邮箱已注册，请直接登录";
  if (normalized.includes("password is too common")) return "该密码过于常见，请换一个更安全的密码";
  if (normalized.includes("system already initialized")) return "系统已完成初始化，请直接登录";
  return message;
}
