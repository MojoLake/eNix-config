import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.on("input", async (event, ctx) => {
    if (!ctx.hasUI || event.source !== "interactive") return;
    await pi.exec("@NOTIFY_COMMAND@", [
      "capture", "pi",
      JSON.stringify({ title: pi.getSessionName(), cwd: ctx.cwd,
        session_id: ctx.sessionManager.getSessionId() }),
    ], { timeout: 6000 });
  });
  pi.on("agent_settled", async (_event, ctx) => {
    if (!ctx.hasUI || !ctx.isIdle()) return;
    await pi.exec("@NOTIFY_COMMAND@", [
      "pi",
      JSON.stringify({ title: pi.getSessionName(), cwd: ctx.cwd,
        session_id: ctx.sessionManager.getSessionId() }),
    ], { timeout: 6000 });
  });
}
