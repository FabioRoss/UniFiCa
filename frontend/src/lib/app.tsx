import { createContext, useContext, type ReactNode } from "react";
import type { AppConfig } from "../api";
import { useFetch } from "./useFetch";

const Ctx = createContext<AppConfig | null>(null);

export function ConfigProvider({ children }: { children: ReactNode }) {
  const { data } = useFetch<AppConfig>("/api/config");
  return <Ctx.Provider value={data}>{children}</Ctx.Provider>;
}

export function useConfig(): AppConfig | null {
  return useContext(Ctx);
}
