import type { Metadata } from "next";

import { AppQueryProvider } from "@/shared/api/query-provider";
import { ThemeScript } from "@/shared/theme/theme-script";

import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "升拓·科研项目申报助手",
  description: "面向政府科研项目申报的智能体工作台",
  icons: {
    icon: "/favicon.svg",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" data-theme="dark" className="dark" suppressHydrationWarning>
      <head>
        <ThemeScript />
      </head>
      <body>
        <AppQueryProvider>{children}</AppQueryProvider>
      </body>
    </html>
  );
}
