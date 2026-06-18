export interface AppInfo {
  name: string;
  version: string;
}

export function appInfo(): AppInfo {
  return { name: "Investment Risk Platform", version: "0.1.0" };
}
