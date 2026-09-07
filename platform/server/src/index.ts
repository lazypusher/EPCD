import Fastify, { type FastifyInstance } from "fastify";
import { loadConfig } from "./epcd/bridge.js";
import { openDb } from "./db.js";
import { artifactRoutes } from "./routes/artifacts.js";
import { epcdRoutes } from "./routes/epcd.js";
import { eventRoutes } from "./routes/events.js";
import { taskRoutes } from "./routes/tasks.js";

export function buildServer(): FastifyInstance {
  const app = Fastify({ logger: { level: "info" } });
  const config = loadConfig();
  const db = openDb(config.dbPath);

  app.get("/health", async () => ({
    ok: true,
    service: "epcd-platform-server",
    version: "0.1.0",
    defaultServer: config.defaultServer,
    time: new Date().toISOString(),
  }));

  void app.register(epcdRoutes);
  void app.register(taskRoutes, db);
  void app.register(eventRoutes, db);
  void app.register(artifactRoutes, db);

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