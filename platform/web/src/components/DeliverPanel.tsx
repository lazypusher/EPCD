import { useQuery } from "@tanstack/react-query";
import { StateDot } from "@deepseek-ai/dsh-client-ui-primitives";
import { api } from "../api/client";
import type { ArtifactCard, Delivery } from "../types";

function baseName(p?: string | null): string | undefined {
  if (!p) return undefined;
  return p.split(/[\\/]/).pop();
}

const IMAGE_TYPES = new Set(["objective-chart", "target-chart", "layout-preview-image"]);

const COMPARISON_SYMBOL: Record<string, string> = {
  equal: "≈",
  "greater-than": "≥",
  "less-than": "≤",
};

export function DeliverPanel({ taskId, delivery }: { taskId: string; delivery: Delivery }) {
  const metrics = delivery.metrics;
  const images = delivery.cards.filter((c) => IMAGE_TYPES.has(c.type));
  const files = delivery.cards.filter((c) => !IMAGE_TYPES.has(c.type));
  const allSatisfied = metrics?.targetValues.every((m) => m.satisfied) ?? false;
  const hasUnsatisfied = metrics ? metrics.targetValues.some((m) => !m.satisfied) : false;

  const adviceQ = useQuery({
    queryKey: ["advice", taskId],
    queryFn: () => api.getAdvice(taskId),
    enabled: hasUnsatisfied,
  });

  return (
    <div>
      {metrics && (
        <section style={{ margin: "12px 0" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <h3 style={{ margin: 0 }}>设计指标达成</h3>
            <StateDot state={allSatisfied ? "done" : "error"} />
            {typeof metrics.objectiveCost === "number" && (
              <code style={{ fontSize: 12 }}>
                总目标代价 objectiveCost = {metrics.objectiveCost.toFixed(5)}
              </code>
            )}
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))",
              gap: 12,
              marginTop: 12,
            }}
          >
            {metrics.targetValues.map((m, i) => (
              <div
                key={i}
                style={{
                  border: "1px solid var(--dsw-border, #ccc)",
                  borderRadius: 10,
                  padding: 12,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong>{m.metric}</strong>
                  <StateDot state={m.satisfied ? "done" : "error"} />
                </div>
                {m.frequency && (
                  <div style={{ fontSize: 12, color: "var(--dsw-text-tertiary, #888)" }}>
                    {m.frequency.value} {m.frequency.unit}
                  </div>
                )}
                <div style={{ marginTop: 6 }}>
                  目标 {COMPARISON_SYMBOL[m.comparison] ?? m.comparison} {m.targetValue} {m.unit}
                </div>
                <div>
                  实际 {Number(m.actualValue).toFixed(4)} {m.unit}
                </div>
                {typeof m.relativeDeviation === "number" && (
                  <div style={{ fontSize: 12, color: m.satisfied ? "var(--dsw-success, #0a7)" : "var(--dsw-danger, red)" }}>
                    偏差 {(m.relativeDeviation * 100).toFixed(2)}%
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {hasUnsatisfied && (
        <section
          style={{
            margin: "12px 0",
            border: "1px solid var(--dsw-border, #ccc)",
            borderRadius: 10,
            padding: 12,
          }}
        >
          <h3 style={{ marginTop: 0 }}>
            优化建议
            {adviceQ.data && (
              <span style={{ fontSize: 12, marginLeft: 10, color: "var(--dsw-text-tertiary, #888)" }}>
                {adviceQ.data.source === "llm" ? "LLM 生成" : "规则建议"}
              </span>
            )}
          </h3>
          {adviceQ.isLoading && <p>生成建议中…</p>}
          {adviceQ.data && (
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {adviceQ.data.advice.map((a, i) => (
                <li key={i} style={{ marginBottom: 6 }}>
                  {a}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {images.length > 0 && (
        <section style={{ margin: "12px 0" }}>
          <h3>图表与三视图</h3>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
            {images.map((c, i) => {
              const file = baseName(c.localPath);
              if (!file) return null;
              return (
                <figure
                  key={i}
                  style={{ margin: 0, border: "1px solid var(--dsw-border, #eee)", borderRadius: 10, overflow: "hidden" }}
                >
                  <img
                    src={api.artifactUrl(taskId, file)}
                    alt={c.title}
                    style={{ width: "100%", display: "block", background: "#fafafa" }}
                  />
                  <figcaption style={{ fontSize: 12, padding: "6px 10px" }}>
                    {c.title}
                    <a
                      href={api.artifactUrl(taskId, file)}
                      target="_blank"
                      rel="noreferrer"
                      style={{ marginLeft: 10, fontSize: 12 }}
                    >
                      原图
                    </a>
                  </figcaption>
                </figure>
              );
            })}
          </div>
        </section>
      )}

      {files.length > 0 && (
        <section style={{ margin: "12px 0" }}>
          <h3>产物文件</h3>
          <DownloadList taskId={taskId} cards={files} />
        </section>
      )}
    </div>
  );
}

function DownloadList({ taskId, cards }: { taskId: string; cards: ArtifactCard[] }) {
  return (
    <ul style={{ listStyle: "none", padding: 0 }}>
      {cards.map((c, i) => {
        const file = baseName(c.localPath) ?? baseName(c.remotePath);
        return (
          <li
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "6px 0",
              borderBottom: "1px solid var(--dsw-border, #eee)",
            }}
          >
            <span style={{ minWidth: 120, fontSize: 13 }}>{c.title}</span>
            <code style={{ fontSize: 12, color: "var(--dsw-text-tertiary, #888)" }}>
              {file ?? c.remotePath}
            </code>
            {file && (
              <a href={api.artifactUrl(taskId, file)} download style={{ marginLeft: "auto", fontSize: 13 }}>
                下载
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}