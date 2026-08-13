"use client";

import { useMutation } from "@tanstack/react-query";
import {
  CheckCircle2Icon,
  FolderIcon,
  FolderOpenIcon,
  Loader2Icon,
} from "lucide-react";

import { selectNewProjectDirectory } from "@/features/projects/api";
import type { NewProjectDirectoryMode } from "@/features/projects/new-project-directory";

interface NewProjectDirectoryFieldProps {
  mode: NewProjectDirectoryMode;
  rootPath: string;
  disabled?: boolean;
  onChange: (mode: NewProjectDirectoryMode, rootPath: string) => void;
}

export function NewProjectDirectoryField({
  mode,
  rootPath,
  disabled = false,
  onChange,
}: NewProjectDirectoryFieldProps) {
  const selectDirectory = useMutation({
    mutationFn: () => selectNewProjectDirectory(rootPath || null),
    onSuccess: (result) => {
      if (result.selected && result.root_path) {
        onChange("custom", result.root_path);
      }
    },
  });

  const isDisabled = disabled || selectDirectory.isPending;

  return (
    <div className="new-project-directory-field">
      <div className="new-project-directory-label">
        <span>工作路径</span>
        <strong>必选</strong>
      </div>

      <div className="new-project-path-options">
        <button
          type="button"
          className={
            mode === "default"
              ? "new-project-path-option active"
              : "new-project-path-option"
          }
          disabled={isDisabled}
          onClick={() => onChange("default", "")}
        >
          <FolderIcon size={18} />
          <span>
            <b>使用默认路径</b>
            <small>由系统统一创建和管理项目目录</small>
          </span>
          {mode === "default" ? <CheckCircle2Icon size={17} /> : null}
        </button>

        <button
          type="button"
          className={
            mode === "custom"
              ? "new-project-path-option active"
              : "new-project-path-option"
          }
          disabled={isDisabled}
          onClick={() => onChange("custom", rootPath)}
        >
          <FolderOpenIcon size={18} />
          <span>
            <b>选择自定义路径</b>
            <small>保存到电脑上的指定文件夹</small>
          </span>
          {mode === "custom" ? <CheckCircle2Icon size={17} /> : null}
        </button>
      </div>

      {mode === "custom" ? (
        <div className="new-project-custom-path">
          <button
            type="button"
            className="ghost-btn"
            disabled={isDisabled}
            onClick={() => selectDirectory.mutate()}
          >
            {selectDirectory.isPending ? (
              <Loader2Icon className="spin" size={15} />
            ) : (
              <FolderOpenIcon size={15} />
            )}
            {selectDirectory.isPending
              ? "请在系统窗口中选择"
              : rootPath
                ? "重新选择文件夹"
                : "选择电脑目录"}
          </button>
          <span title={rootPath || undefined}>
            {rootPath || "尚未选择文件夹"}
          </span>
        </div>
      ) : null}

      {selectDirectory.isError ? (
        <p className="new-project-directory-error">
          {selectDirectory.error instanceof Error
            ? selectDirectory.error.message
            : "无法打开文件夹选择器，请稍后重试。"}
        </p>
      ) : null}
    </div>
  );
}
