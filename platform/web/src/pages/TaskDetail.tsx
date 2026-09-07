import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { Button, JsonTree, Pill } from "@deepseek-ai/dsh-client-ui-primitives";
import { api } from "../api/client";
import { getToken } from "../auth";
import { PhaseStepper } from "../components/PhaseStepper";
import { MilestoneCard } from "../components/MilestoneCard";
import { OptimizationPanel } from "../components/OptimizationPanel";
import { DeliverPanel } from "../components/DeliverPanel";
import type { MilestoneCode, MilestoneDecision } from "../types";
import { PHASE_LABELS } from "../types";

const MILESTONE_ORDER: MilestoneCode[] = ["M1", "M2", "M3", "M4"];

export function TaskDetail() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["task", id],
    queryFn: () => api.getTask(id),
    refetchInterval: (query) => {
      const ctx = query.state.data;
      return ctx?.task.status === "running" ? 2000 : false;
    },
  });

  const startMut = useMutation({
    mutationFn: () => api.startTask(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", id] }),
  });

  const confirmMut = useMutation({
    mutationFn: (args: { code: MilestoneCode; decision: MilestoneDecision; config?: Record<string, unknown> }) =>
      api.confirmMilestone(id, args.code, args.decision, args.config),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["task", id] }),
  });

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [optimization, setOptimization] = useState<any>(null);

  // 实时通道：running/optimizing 时订阅 SSE，收到状态推送 + 优化进度
  useEffect(() => {
    const status = data?.task.status;
    if (status !== "optimizing" && status !== "running") return;
    const es = new EventSource(`/api/tasks/${id}/events?token=${getToken() ?? ""}`);
    es.addEventListener("status", (ev) => {
      const snap = JSON.parse((ev as MessageEvent).data);
      setOptimization(snap.optimization ?? null);
      if (snap.task?.status !== "optimizing") {
        qc.invalidateQueries({ queryKey: ["task", id] });
      }
    });
    return () => es.close();
  }, [id, data?.task.status, qc]);

  const deliveryQ = useQuery({
    queryKey: ["delivery", id],
    queryFn: () => api.getDelivery(id),
    enabled: data?.task.status === "delivered",
  });

  if (isLoading) return <div style={{ padding: 24 }}>加载中…</div>;
  if (isError || !data) return <div style={{ padding: 24 }}>任务不存在或加载失败。</div>;

  const ctx = data;
  const awaiting = ctx.milestones.find((m) => m.status === "awaiting");

  return (
    <div style={{ padding: 24, maxWidth: 920 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <Link to="/">← 返回</Link>
        <h2 style={{ margin: 0 }}>{ctx.task.name}</h2>
        <Pill active>{ctx.task.status}</Pill>
        <code style={{ fontSize: 12 }}>{ctx.task.server}</code>
      </div>

      <PhaseStepper ctx={ctx} />

      {ctx.task.status === "created" && (
        <div style={{ margin: "12px 0" }}>
          <Button variant="primary" onClick={() => startMut.mutate()} disabled={startMut.isPending}>
            {startMut.isPending ? "启动中…" : "一键启动自动流转"}
          </Button>
        </div>
      )}

      {ctx.task.status === "running" && (
        <p style={{ color: "var(--dsw-text-secondary, #666)" }}>
          正在执行「{PHASE_LABELS[ctx.task.current_phase]}」阶段（自动轮询中）…
        </p>
      )}

      {ctx.task.status === "optimizing" && (
        <div>
          <p style={{ color: "var(--dsw-text-secondary, #666)" }}>
            正在迭代优化（后台执行，SSE 实时更新）…
          </p>
          <OptimizationPanel taskId={id} snapshot={optimization} />
        </div>
      )}

      {ctx.task.status === "awaiting_confirmation" && awaiting && (
        <div>
          <h3>待确认里程碑</h3>
          <MilestoneCard
            code={awaiting.code}
            milestone={awaiting}
            disabled={confirmMut.isPending}
            onDecision={(code, decision, config) =>
              confirmMut.mutate({ code, decision, config })
            }
          />
          {confirmMut.isError && (
            <p style={{ color: "var(--dsw-danger, red)" }}>
              {(confirmMut.error as Error).message}
            </p>
          )}
        </div>
      )}

      {(ctx.task.status === "delivered" || ctx.task.status === "failed" || ctx.task.status === "aborted") && (
        <div style={{ margin: "12px 0" }}>
          <Pill active>状态：{ctx.task.status}</Pill>
        </div>
      )}

      {ctx.task.status === "delivered" && deliveryQ.data?.delivered && (
        <DeliverPanel taskId={id} delivery={deliveryQ.data} />
      )}

      <h3>阶段日志</h3>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {ctx.phases.map((p, i) => (
          <li key={i} style={{ padding: "6px 0", borderBottom: "1px solid var(--dsw-border, #eee)" }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
              <Pill>{PHASE_LABELS[p.phase]}</Pill>
              <code>{p.status}</code>
            </div>
            {p.error != null && (
              <div style={{ marginTop: 6 }}>
                <JsonTree data={p.error as object} label="错误" />
              </div>
            )}
            {p.payload != null && (
              <div style={{ marginTop: 6 }}>
                <JsonTree data={p.payload as object} label="产出" expandTopLevel />
              </div>
            )}
          </li>
        ))}
      </ul>

      <h3>里程碑</h3>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {MILESTONE_ORDER.map((code) => {
          const m = ctx.milestones.find((x) => x.code === code);
          if (!m) return null;
          return (
            <li key={code} style={{ padding: "6px 0" }}>
              <Pill active={m.status === "awaiting"}>
                {code} · {m.status}
              </Pill>
            </li>
          );
        })}
      </ul>
    </div>
  );
}