import { formatRelativeTime } from "@/lib/format";
import type { StoryStage } from "@/lib/auditStory";
import { cn } from "@/lib/utils";

type StoryStageRailProps = {
  stages: StoryStage[];
  compact?: boolean;
  className?: string;
};

function stageToneClasses(stage: StoryStage) {
  if (stage.status === "failed") {
    return {
      frame: "border-rose-200 bg-rose-50/90",
      dot: "bg-rose-500 shadow-[0_0_0_6px_rgba(244,63,94,0.12)]",
      label: "text-rose-700",
    };
  }

  if (stage.status === "active") {
    return {
      frame: "border-cyan-200 bg-cyan-50/90 story-card-live",
      dot: "bg-cyan-500 shadow-[0_0_0_7px_rgba(14,165,233,0.14)]",
      label: "text-cyan-700",
    };
  }

  if (stage.status === "complete") {
    if (stage.tone === "danger") {
      return {
        frame: "border-rose-200 bg-rose-50/85",
        dot: "bg-rose-500",
        label: "text-rose-700",
      };
    }

    if (stage.tone === "warning") {
      return {
        frame: "border-amber-200 bg-amber-50/90",
        dot: "bg-amber-500",
        label: "text-amber-700",
      };
    }

    if (stage.tone === "success") {
      return {
        frame: "border-emerald-200 bg-emerald-50/90",
        dot: "bg-emerald-500 shadow-[0_0_0_6px_rgba(16,185,129,0.12)]",
        label: "text-emerald-700",
      };
    }

    return {
      frame: "border-slate-200 bg-white",
      dot: "bg-slate-700",
      label: "text-slate-700",
    };
  }

  return {
    frame: "border-slate-200 bg-slate-50/85",
    dot: "bg-slate-300",
    label: "text-slate-500",
  };
}

function stageStatusLabel(stage: StoryStage) {
  switch (stage.status) {
    case "active":
      return "Live";
    case "complete":
      return "Done";
    case "failed":
      return "Blocked";
    default:
      return "Queued";
  }
}

export function StoryStageRail({ stages, compact = false, className }: Readonly<StoryStageRailProps>) {
  return (
    <div
      className={cn(
        "grid gap-3",
        compact ? "sm:grid-cols-2 xl:grid-cols-4" : "md:grid-cols-2 xl:grid-cols-4",
        className,
      )}
    >
      {stages.map((stage) => {
        const tone = stageToneClasses(stage);

        return (
          <article key={stage.id} className={cn("rounded-[1.25rem] border px-4 py-4", tone.frame)}>
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span
                  className={cn(
                    "inline-flex h-3.5 w-3.5 rounded-full transition-transform",
                    tone.dot,
                    stage.status === "active" && "story-pulse",
                  )}
                />
                <p className={cn("text-[11px] font-semibold uppercase tracking-[0.18em]", tone.label)}>{stageStatusLabel(stage)}</p>
              </div>
              {stage.timestamp ? (
                <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-slate-500">
                  {formatRelativeTime(stage.timestamp)}
                </p>
              ) : null}
            </div>

            <h3 className={cn("mt-3 text-sm font-semibold tracking-[-0.02em]", compact ? "text-[0.95rem]" : "text-base", "text-slate-950")}>
              {stage.label}
            </h3>
            <p className={cn("mt-2 text-sm leading-6 text-slate-600", compact && "text-[13px] leading-5")}>{stage.detail}</p>
          </article>
        );
      })}
    </div>
  );
}
