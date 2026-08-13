"use client";

import { PanelLeftCloseIcon, PanelLeftOpenIcon } from "lucide-react";
import { useState } from "react";

interface SidePanelProps {
  children: React.ReactNode;
  title?: string;
  defaultCollapsed?: boolean;
}

export function SidePanel({ children, title, defaultCollapsed = false }: SidePanelProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <aside className={`side-panel${collapsed ? " collapsed" : ""}`}>
      {/* Header */}
      {title && !collapsed && (
        <div className="side-panel-head">
          <span className="side-panel-title">{title}</span>
          <button
            className="side-panel-toggle"
            onClick={() => setCollapsed(true)}
            aria-label="折叠面板"
          >
            <PanelLeftCloseIcon size={16} />
          </button>
        </div>
      )}

      {/* Body */}
      {!collapsed && <div className="side-panel-body">{children}</div>}

      {/* Collapsed mode: show expand button */}
      {collapsed && (
        <div className="side-panel-collapsed">
          <button
            className="side-panel-expand"
            onClick={() => setCollapsed(false)}
            aria-label="展开面板"
            title={title}
          >
            <PanelLeftOpenIcon size={16} />
          </button>
        </div>
      )}
    </aside>
  );
}
