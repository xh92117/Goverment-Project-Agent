export type NewProjectDirectoryMode = "default" | "custom" | null;

export function isNewProjectDirectoryReady(
  mode: NewProjectDirectoryMode,
  rootPath: string,
) {
  return mode === "default" || (mode === "custom" && Boolean(rootPath.trim()));
}

export function newProjectRootPath(
  mode: NewProjectDirectoryMode,
  rootPath: string,
) {
  return mode === "custom" && rootPath.trim() ? rootPath.trim() : null;
}
