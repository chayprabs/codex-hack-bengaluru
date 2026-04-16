"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { apiClient, getApiErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

type DemoLaunchButtonProps = {
  idleLabel?: string;
  pendingLabel?: string;
  className?: string;
};

export function DemoLaunchButton({
  idleLabel = "Open demo",
  pendingLabel = "Opening demo...",
  className,
}: Readonly<DemoLaunchButtonProps>) {
  const router = useRouter();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  async function handleClick() {
    setErrorMessage(null);

    try {
      const audit = await apiClient.createDemoAudit();
      startTransition(() => {
        router.push(`/audit/${audit.id}`);
      });
    } catch (error) {
      setErrorMessage(getApiErrorMessage(error));
    }
  }

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={() => void handleClick()}
        disabled={isPending}
        className={cn(
          "inline-flex min-h-10 items-center justify-center rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-800 transition hover:border-slate-300 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60",
          className,
        )}
      >
        {isPending ? pendingLabel : idleLabel}
      </button>

      {errorMessage ? <p className="text-sm leading-6 text-rose-700">{errorMessage}</p> : null}
    </div>
  );
}
