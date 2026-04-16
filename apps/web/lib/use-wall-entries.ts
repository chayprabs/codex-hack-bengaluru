"use client";

import { useEffect, useState } from "react";

import {
  apiClient,
  getApiErrorMessage,
  getApiErrorStatus,
  type WallEntry,
} from "@/lib/api";

type LoadStatus = "loading" | "ready" | "error";

type WallEntriesState = {
  entries: WallEntry[];
  status: LoadStatus;
  error: string | null;
  errorStatus: number | null;
};

export function useWallEntries() {
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState<WallEntriesState>({
    entries: [],
    status: "loading",
    error: null,
    errorStatus: null,
  });

  useEffect(() => {
    let disposed = false;

    setState((current) => ({
      ...current,
      status: current.entries.length ? "ready" : "loading",
      error: null,
      errorStatus: null,
    }));

    async function loadEntries() {
      try {
        const entries = await apiClient.getWall();

        if (disposed) {
          return;
        }

        setState({
          entries,
          status: "ready",
          error: null,
          errorStatus: null,
        });
      } catch (error) {
        if (disposed) {
          return;
        }

        setState({
          entries: [],
          status: "error",
          error: getApiErrorMessage(error),
          errorStatus: getApiErrorStatus(error),
        });
      }
    }

    void loadEntries();

    return () => {
      disposed = true;
    };
  }, [reloadToken]);

  return {
    ...state,
    refresh: () => setReloadToken((current) => current + 1),
  };
}
