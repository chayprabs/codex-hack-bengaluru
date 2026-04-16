import type { ReactNode } from "react";

import type { AuditState } from "@/lib/types";
import { formatDateTime } from "@/lib/format";
import { cn, repoLabelFromUrl, shortId } from "@/lib/utils";
import { StatusBadge, formatStatusLabel, toneFromAuditStatus } from "@/components/StatusBadge";

type AuditHeaderProps = {
  auditId: string;
  repoUrl: string;
  status?: AuditState;
  createdAt?: string;
  updatedAt?: string;
  findingsCount?: number;
  actions?: ReactNode;
  isLoading?: boolean;
  className?: string;
};

function AuditHeaderSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      <div className="h-4 w-24 animate-pulse rounded-full bg-slate-200" />
      <div className="h-10 w-72 max-w-full animate-pulse rounded-2xl bg-slate-100" />
      <div className="h-4 w-full max-w-xl animate-pulse rounded-full bg-slate-100" />
      <div className="grid gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((item) => (
          <div key={item} className="h-16 animate-pulse rounded-2xl bg-slate-100" />
        ))}
      </div>
    </div>
  );
}

export function AuditHeader({
  auditId,
  repoUrl,
  status,
  createdAt,
  updatedAt,
  findingsCount,
  actions,
  isLoading = false,
  className,
}: Readonly<AuditHeaderProps>) {
  if (isLoading) {
    return (
      <header className={cn("rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6", className)}>
        <AuditHeaderSkeleton />
      </header>
    );
  }

  return (
    <header className={cn("rounded-[1.75rem] border border-slate-200 bg-white/90 p-5 shadow-sm sm:p-6", className)}>
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">Audit room</p>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <h1 className="min-w-0 break-all text-3xl font-semibold tracking-[-0.04em] text-slate-950 sm:text-4xl">
              {repoLabelFromUrl(repoUrl)}
            </h1>
            {status ? (
              <StatusBadge tone={toneFromAuditStatus(status)} mono>
                {formatStatusLabel(status)}
              </StatusBadge>
            ) : null}
          </div>
          <p className="mt-3 break-all font-mono text-sm text-slate-600">{repoUrl}</p>
        </div>

        {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
      </div>

      <dl className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Audit id</dt>
          <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">{shortId(auditId, 12)}</dd>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Created</dt>
          <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">
            {createdAt ? formatDateTime(createdAt) : "Unknown"}
          </dd>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Last update</dt>
          <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">
            {updatedAt ? formatDateTime(updatedAt) : "Unknown"}
          </dd>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3">
          <dt className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Findings</dt>
          <dd className="mt-2 font-mono text-sm font-semibold text-slate-950">
            {findingsCount === undefined ? "N/A" : findingsCount}
          </dd>
        </div>
      </dl>
    </header>
  );
}
