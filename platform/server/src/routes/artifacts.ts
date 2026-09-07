import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type { FastifyInstance } from "fastify";
import type { Db } from "../db.js";
import { getPhaseLogs } from "../tasks/store.js";

interface ArtifactCard {
  type: string;
  title: string;
  remotePath?: string | null;
  localPath?: string | null;
}

interface DeliveryPayload {
  job_id?: string;
  cards: ArtifactCard[];
}

function getDeliveryPayload(db: Db, taskId: string): DeliveryPayload | null {
  const logs = getPhaseLogs(db, taskId);
  for (let i = logs.length - 1; i >= 0; i--) {
    const l = logs[i];
    if (l.phase !== "deliver" || l.status !== "succeeded" || !l.payload_json) continue;
    try {
      const p = JSON.parse(l.payload_json) as {
        job_id?: string;
        cards?: ArtifactCard[];
      };
      return { job_id: p.job_id, cards: p.cards ?? [] };
    } catch {
      return null;
    }
  }
  return null;
}

function readObjectiveValues(cards: ArtifactCard[]) {
  const card = cards.find((c) => c.type === "objective-values" && c.localPath);
  if (!card?.localPath || !existsSync(card.localPath)) return null;
  try {
    const obj = JSON.parse(readFileSync(card.localPath, "utf8")) as {
      targetValues?: unknown[];
      objectiveCost?: number;
    };
    return { targetValues: obj.targetValues ?? [], objectiveCost: obj.objectiveCost };
  } catch {
    return null;
  }
}

const MIME: Record<string, string> = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".gif": "image/gif",
  ".json": "application/json",
  ".csv": "text/csv",
  ".txt": "text/plain",
  ".gtxt": "text/plain",
  ".snp": "text/plain",
  ".md": "text/markdown",
};

function mimeFor(file: string): string {
  return MIME[path.extname(file).toLowerCase()] ?? "application/octet-stream";
}

export async function artifactRoutes(app: FastifyInstance, db: Db): Promise<void> {
  app.get("/api/tasks/:id/delivery", async (req) => {
    const { id } = req.params as { id: string };
    const delivery = getDeliveryPayload(db, id);
    if (!delivery) {
      return { ok: true, delivered: false, job_id: null, cards: [], metrics: null };
    }
    return {
      ok: true,
      delivered: true,
      job_id: delivery.job_id ?? null,
      cards: delivery.cards,
      metrics: readObjectiveValues(delivery.cards),
    };
  });

  app.get("/api/tasks/:id/artifacts/:file", async (req, reply) => {
    const { id, file } = req.params as { id: string; file: string };
    const delivery = getDeliveryPayload(db, id);
    if (!delivery) return reply.code(404).send({ ok: false, error: { message: "no delivery" } });

    const name = path.basename(file); // 防路径穿越
    const card = delivery.cards.find(
      (c) => c.localPath && path.basename(c.localPath) === name
    );
    if (!card?.localPath) {
      return reply.code(404).send({ ok: false, error: { message: `artifact not found: ${name}` } });
    }
    if (!existsSync(card.localPath)) {
      return reply.code(404).send({ ok: false, error: { message: "local copy missing" } });
    }
    const buf = readFileSync(card.localPath);
    reply
      .type(mimeFor(name))
      .header("Content-Disposition", `inline; filename="${name}"`)
      .send(buf);
    return reply;
  });
}