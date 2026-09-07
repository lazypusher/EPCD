import type { FastifyInstance } from "fastify";
import { loadConfig, loadServers } from "../epcd/bridge.js";

export async function serverRoutes(app: FastifyInstance): Promise<void> {
  const config = loadConfig();
  app.get("/api/servers", async () => {
    return { ok: true, servers: loadServers(config) };
  });
}