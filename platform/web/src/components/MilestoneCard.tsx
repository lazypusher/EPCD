import { useState } from "react";
import { Button, JsonTree } from "@deepseek-ai/dsh-client-ui-primitives";
import type { MilestoneCode, Milestone } from "../types";

const TITLES: Record<MilestoneCode, string> = {
  M1: "模板与实例选定",
  M2: "目标与仿真配置",
  M3: "最优参数写回",
  M4: "最终仿真结果",
};

interface Props {
  code: MilestoneCode;
  milestone: Milestone;
  disabled: boolean;
  onDecision: (
    code: MilestoneCode,
    decision: "approve" | "modify" | "abort",
    config?: Record<string, unknown>
  ) => void;
}

export function MilestoneCard({ code, milestone, disabled, onDecision }: Props) {
  const [mode, setMode] = useState<"view" | "modify">("view");
  const [jsonText, setJsonText] = useState("");

  const isAwaiting = milestone.status === "awaiting";

  function handleModify() {
    if (mode === "view") {
      setMode("modify");
      setJsonText(JSON.stringify(milestone.snapshot ?? {}, null, 2));
      return;
    }
    let config: Record<string, unknown>;
    try {
      config = JSON.parse(jsonText);
    } catch {
      alert("JSON 解析失败，请检查格式");
      return;
    }
    onDecision(code, "modify", config);
    setMode("view");
  }

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
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <h3 style={{ margin: 0 }}>{code} · {TITLES[code]}</h3>
        <code style={{ fontSize: 12, color: "var(--dsw-text-tertiary, #888)" }}>
          {milestone.status}
        </code>
      </div>

      {isAwaiting && !milestone.snapshot && (
        <p style={{ color: "var(--dsw-text-secondary, #666)" }}>无快照数据</p>
      )}

      {isAwaiting && milestone.snapshot != null && mode === "view" && (
        <div style={{ margin: "10px 0" }}>
          <JsonTree data={milestone.snapshot as object} label={`${code} 快照`} expandTopLevel />
        </div>
      )}

      {mode === "modify" && (
        <textarea
          value={jsonText}
          onChange={(e) => setJsonText(e.target.value)}
          rows={10}
          style={{ width: "100%", fontFamily: "monospace", fontSize: 12, marginTop: 10 }}
        />
      )}

      {isAwaiting && (
        <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
          {mode === "view" ? (
            <>
              <Button variant="primary" disabled={disabled} onClick={() => onDecision(code, "approve")}>
                批准
              </Button>
              <Button variant="outline" disabled={disabled} onClick={handleModify}>
                修改
              </Button>
              <Button variant="ghost" disabled={disabled} onClick={() => onDecision(code, "abort")}>
                终止
              </Button>
            </>
          ) : (
            <>
              <Button variant="primary" disabled={disabled} onClick={handleModify}>
                应用修改并重跑
              </Button>
              <Button variant="ghost" onClick={() => setMode("view")}>
                取消
              </Button>
            </>
          )}
        </div>
      )}
    </div>
  );
}