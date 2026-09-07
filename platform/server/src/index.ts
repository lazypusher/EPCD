import fs from "node:fs";
import path from "node:path";
import Fastify, { type FastifyInstance } from "fastify";
import { loadConfig } from "./epcd/bridge.js";
import { epcdRoutes } from "./routes/epcd.js";

export function buildServer(): FastifyInstance {
  const app = Fastify({ logger: { level: "info" } });
  const config = loadConfig();

  // 确保会话 SQLite 所在目录存在
  fs.mkdirSync(path.dirname(config.dbPath), { recursive: true });

  app.get("/health", async () => ({
    ok: true,
    service: "epcd-platform-server",
    version: "0.1.0",
    config: {
      defaultServer: config.defaultServer,
      backendDir: config.backendDir,
      dbPath: config.dbPath,
    },
    time: new Date().toISOString(),
  }));

  void app.register(epcdRoutes);

  return app;
}

const isMain =
  process.argv[1] &&
  import.meta.url.endsWith(process.argv[1].replace(/\\/g, "/"));
if (isMain) {
  const port = Number(process.env.PORT ?? 4100);
  const host = process.env.HOST ?? "127.0.0.1";
  const app = buildServer();
  app
    .listen({ port, host })
    .then(() => app.log.info(`EPCD platform server on http://${host}:${port}`));
}