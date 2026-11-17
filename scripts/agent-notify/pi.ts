import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export default function (pi: ExtensionAPI) {
  pi.on("agent_settled", async (_event, ctx) => {
    if (!ctx.hasUI || !ctx.isIdle()) return;
    await pi.exec("@NOTIFY_COMMAND@", [
      "pi",
      JSON.stringify({ title: pi.getSessionName(), cwd: ctx.cwd }),
    ], { timeout: 5000 });
  });
}
