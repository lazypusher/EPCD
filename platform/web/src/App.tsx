import {
  Button,
  Pill,
  StateDot,
  JsonTree,
  MarkdownText,
} from "@deepseek-ai/dsh-client-ui-primitives";

export default function App() {
  return (
    <div style={{ padding: 24, display: "flex", flexDirection: "column", gap: 20, maxWidth: 720 }}>
      <h1>EPCD Platform</h1>
      <p>DSH primitives 验证（Cordis-free React 组件，经 <code>--dsw-*</code> token 着色）：</p>

      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <Button variant="primary">Primary</Button>
        <Button variant="outline">Outline</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="toolbar">Toolbar</Button>
        <Pill active>active pill</Pill>
        <Pill>static pill</Pill>
        <StateDot state="done" />
        <StateDot state="ongoing" />
        <StateDot state="warning" />
        <StateDot state="error" />
      </div>

      <div>
        <strong>MarkdownText</strong>
        <MarkdownText
          text={"# 标题\n\n- 列表项 A\n- 列表项 B\n\n**加粗** 与 `code` 与 $x^2$"}
        />
      </div>

      <div>
        <strong>JsonTree</strong>
        <JsonTree
          data={{ ok: true, health: { status: "ok" }, modules: ["project", "param", "tech"] }}
          label="epcd_health 响应"
          copyable
          expandTopLevel
        />
      </div>
    </div>
  );
}