import Fastify, { type FastifyInstance } from "fastify";

export function buildServer(): FastifyInstance {
  const app = Fastify({ logger: { level: "info" } });

  app.get("/health", async () => ({
    ok: true,
    service: "epcd-platform-server",
    version: "0.1.0",
    time: new Date().toISOString(),
  }));

  return app;
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].replace(/\\/g, "/"));
if (isMain || import.meta.url.endsWith("/src/index.ts")) {
  const port = Number(process.env.PORT ?? 4100);
  const host = process.env.HOST ?? "127.0.0.1";
  const app = buildServer();
  app.listen({ port, host }).then(() => {
    app.log.info(`EPCD platform server listening on http://${host}:${port}`);
  });
}