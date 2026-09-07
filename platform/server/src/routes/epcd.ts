import type { FastifyInstance } from "fastify";
import {
  EPCD_TOOLS,
  TOOL_ROUTES,
  loadConfig,
  runEpcdTool,
} from "../epcd/bridge.js";

interface ToolBody {
  input?: unknown;
  server?: string;
  session?: string;
  ssh?: string;
  pkg?: string;
}

export async function epcdRoutes(app: FastifyInstance): Promise<void> {
  const config = loadConfig();

  app.get("/api/epcd/tools", async () => ({
    tools: EPCD_TOOLS.map((tool) => ({ tool, route: `/api/epcd${TOOL_ROUTES[tool]}` })),
    defaultServer: config.defaultServer,
  }));

  for (const tool of EPCD_TOOLS) {
    app.post(`/api/epcd${TOOL_ROUTES[tool]}`, async (req, reply) => {
      const body = (req.body ?? {}) as ToolBody;

      let result;
      try {
        result = await runEpcdTool(
          {
            tool,
            input: body.input,
            server: body.server,
            session: body.session,
            ssh: body.ssh,
            pkg: body.pkg,
          },
          config
        );
      } catch (err) {
        req.log.error({ err }, "failed to spawn epcd_agent.cli");
        return reply.code(500).send({
          ok: false,
          error: { type: "SPAWN", message: String(err) },
        });
      }

      // exit 2 = usage error（参数/工具名/stderr JSON 非法）→ 400；
      // exit 0/1 = 结构化业务结果 → 200（前端只看 ok 字段）。
      const status = result.exitCode === 2 ? 400 : 200;
      return reply.code(status).send({
        ok: result.ok,
        data: result.data,
        error: result.error,
        exitCode: result.exitCode,
      });
    });
  }
}