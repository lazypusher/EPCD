import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Button, Input, Pill, StateDot } from "@deepseek-ai/dsh-client-ui-primitives";
import { api } from "../api/client";
import type { TaskStatus } from "../types";
import { PHASE_LABELS, type Phase } from "../types";

const STATUS_COLOR: Record<TaskStatus, "done" | "warning" | "ongoing" | "error"> = {
  created: "ongoing",
  running: "ongoing",
  optimizing: "ongoing",
  awaiting_confirmation: "warning",
  confirmed: "done",
  delivered: "done",
  failed: "error",
  aborted: "error",
};

export function TaskList() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["tasks"], queryFn: api.listTasks });

  const [name, setName] = useState("");
  const [server, setServer] = useState("epcd-primary");
  const [workDir, setWorkDir] = useState("");
  const [technology, setTechnology] = useState("/home/zhubo/demo_revised.ptxt");

  const createMut = useMutation({
    mutationFn: api.createTask,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      setName("");
      setWorkDir("");
    },
  });

  function handleCreate() {
    if (!name || !workDir) {
      alert("请填写器件名与远端工作目录");
      return;
    }
    createMut.mutate({
      name,
      server,
      config: {
        projectInput: { action: "init", work_dir: workDir, technology },
        templateInput: { action: "list" },
      },
    });
  }

  return (
    <div style={{ padding: 24, maxWidth: 920 }}>
      <h1>EPCD 器件设计平台</h1>

      <section
        style={{
          border: "1px solid var(--dsw-border, #ccc)",
          borderRadius: 12,
          padding: 16,
          margin: "16px 0",
        }}
      >
        <h3 style={{ marginTop: 0 }}>新建设计任务</h3>
        <div style={{ display: "grid", gap: 10, gridTemplateColumns: "1fr 1fr", maxWidth: 640 }}>
          <label>
            器件名 *
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="如 inductor_4nH" />
          </label>
          <label>
            服务器
            <Input value={server} onChange={(e) => setServer(e.target.value)} />
          </label>
          <label>
            远端工作目录 *
            <Input
              value={workDir}
              onChange={(e) => setWorkDir(e.target.value)}
              placeholder="/home/zhubo/epcd-runs/<器件名>"
            />
          </label>
          <label>
            工艺文件
            <Input value={technology} onChange={(e) => setTechnology(e.target.value)} />
          </label>
        </div>
        <div style={{ marginTop: 12 }}>
          <Button variant="primary" onClick={handleCreate} disabled={createMut.isPending}>
            {createMut.isPending ? "创建中…" : "创建任务"}
          </Button>
          {createMut.isError && (
            <span style={{ color: "var(--dsw-danger, red)", marginLeft: 12 }}>
              {(createMut.error as Error).message}
            </span>
          )}
        </div>
      </section>

      <h3>任务列表</h3>
      {data?.tasks.length === 0 && <p>暂无任务，先创建一个。</p>}
      <ul style={{ listStyle: "none", padding: 0 }}>
        {data?.tasks.map((t) => (
          <li
            key={t.id}
            style={{
              borderBottom: "1px solid var(--dsw-border, #eee)",
              padding: "10px 4px",
              display: "flex",
              alignItems: "center",
              gap: 12,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 200 }}>
              <StateDot state={STATUS_COLOR[t.status as TaskStatus] ?? "ongoing"} />
              <Link to={`/tasks/${t.id}`} style={{ fontWeight: 600 }}>
                {t.name}
              </Link>
            </div>
            <Pill>{PHASE_LABELS[t.current_phase as Phase] ?? t.current_phase}</Pill>
            <code style={{ fontSize: 12, color: "var(--dsw-text-tertiary, #888)" }}>{t.server}</code>
            <span style={{ fontSize: 12, marginLeft: "auto" }}>
              {new Date(t.created_at).toLocaleString()}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}