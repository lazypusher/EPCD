import { StateDot, type StateDotState } from "@deepseek-ai/dsh-client-ui-primitives";
import type { Phase, TaskContext } from "../types";
import { PHASE_LABELS, PHASE_ORDER } from "../types";

function phaseState(phase: Phase, ctx: TaskContext): StateDotState | "pending" {
  const log = ctx.phases.find((p) => p.phase === phase);
  if (log?.status === "succeeded") return "done";
  if (log?.status === "failed") return "error";
  if (ctx.task.current_phase === phase) {
    if (ctx.task.status === "failed" || ctx.task.status === "aborted") return "error";
    if (ctx.task.status === "awaiting_confirmation") return "warning";
    return "ongoing";
  }
  return "pending";
}

export function PhaseStepper({ ctx }: { ctx: TaskContext }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        alignItems: "center",
        flexWrap: "wrap",
        padding: "12px 0",
      }}
    >
      {PHASE_ORDER.map((phase, i) => {
        const state = phaseState(phase, ctx);
        const isCurrent = ctx.task.current_phase === phase;
        return (
          <div key={phase} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {i > 0 && <span style={{ color: "var(--dsw-text-tertiary, #888)" }}>→</span>}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "4px 8px",
                borderRadius: 999,
                border: isCurrent
                  ? "1px solid var(--dsw-border-strong, #999)"
                  : "1px solid transparent",
                opacity: state === "pending" ? 0.45 : 1,
              }}
            >
              <StateDot state={state === "pending" ? "warning" : state} />
              <span style={{ fontSize: 13 }}>{PHASE_LABELS[phase]}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}