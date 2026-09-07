import type { FastifyInstance } from "fastify";
import type { Db } from "../db.js";
import { generateAdvice, type TargetMetric } from "../advice.js";
import { loadConfig } from "../epcd/bridge.js";
import { getDeliveryPayload, readObjectiveValues } from "./artifacts.js";

export async function adviceRoutes(app: FastifyInstance, db: Db): Promise<void> {
  const config = loadConfig();

  app.get("/api/tasks/:id/advice", async (req, reply) => {
    const { id } = req.params as { id: string };
    const delivery = getDeliveryPayload(db, id);
    if (!delivery) {
      return reply.code(404).send({ ok: false, error: { message: "no delivery" } });
    }
    const values = readObjectiveValues(delivery.cards);
    const metrics = (values?.targetValues ?? []) as TargetMetric[];
    const result = await generateAdvice(metrics, config);
    return { ok: true, ...result };
  });
}