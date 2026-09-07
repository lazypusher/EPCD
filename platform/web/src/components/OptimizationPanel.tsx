import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button, Pill } from "@deepseek-ai/dsh-client-ui-primitives";
import { api } from "../api/client";

interface OptimizationSnapshot {
  epcdTaskId: string;
  status: string;
  bestJobId?: string;
  rounds?: unknown[];
  consumed?: unknown;
  jobCount: number;
}

const STATUS_LABEL: Record<string, string> = {
  pending: "待启动",
  running: "迭代中",
  finished: "已完成",
  paused: "已暂停",
};

export function OptimizationPanel({
  taskId,
  snapshot,
}: {
  taskId: string;
  snapshot: OptimizationSnapshot | null;
}) {
  const qc = useQueryClient();
  const cancelMut = useMutation({
    mutationFn: () => api.cancelOptimization(taskId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", taskId] }),
  });

  return (
    <div
      style={{
        border: "1px solid var(--dsw-border, #ccc)",
        borderRadius: 12,
        padding: 16,
        margin: "12px 0",
        maxWidth: 720,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <h3 style={{ margin: 0 }}>优化看板</h3>
        {snapshot && <Pill active>{STATUS_LABEL[snapshot.status] ?? snapshot.status}</Pill>}
        {snapshot && <code style={{ fontSize: 12 }}>{snapshot.epcdTaskId}</code>}
        {cancelMut.isPending ? null : (
          <Button variant="outline" size="sm" onClick={() => cancelMut.mutate()} disabled={cancelMut.isPending}>
            取消优化
          </Button>
        )}
      </div>

      {snapshot && (
        <div style={{ marginTop: 10, display: "flex", gap: 24, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 12, color: "var(--dsw-text-tertiary, #888)" }}>已迭代</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{snapshot.jobCount}</div>
          </div>
          <div>
            <div style={{ fontSize: 12, color: "var(--dsw-text-tertiary, #888)" }}>最优 job</div>
            <div style={{ fontSize: 14 }}>{snapshot.bestJobId ?? "—"}</div>
          </div>
          {typeof snapshot.rounds?.length === "number" && (
            <div>
              <div style={{ fontSize: 12, color: "var(--dsw-text-tertiary, #888)" }}>已记录轮次</div>
              <div style={{ fontSize: 14 }}>{snapshot.rounds.length}</div>
            </div>
          )}
        </div>
      )}

      {cancelMut.isError && (
        <p style={{ color: "var(--dsw-danger, red)" }}>{(cancelMut.error as Error).message}</p>
      )}
    </div>
  );
}