import { routeTelegramCallback, buildCallbackData, CallbackPayload } from "./router";
import { callAntigravityTool } from "./tools/antigravity";
import { registerGithubTools } from "./tools/github";

export interface ToolContent {
  type: "text";
  text: string;
}

export interface ToolResult {
  content: ToolContent[];
}

export interface ToolContext {
  traceId: string;
}

export interface ToolDefinition<TParams> {
  name: string;
  description: string;
  execute: (context: ToolContext, params: TParams) => Promise<ToolResult>;
}

export interface PluginApi {
  registerTool: <TParams>(definition: ToolDefinition<TParams>) => void;
  registerHook: (eventName: "telegram:message", handler: (payload: CallbackPayload) => Promise<void>) => void;
}

export default function registerPlugin(api: PluginApi): void {
  registerGithubTools(api);

  api.registerHook("telegram:message", async (payload: CallbackPayload): Promise<void> => {
    const callback = routeTelegramCallback(payload.text);
    if (callback === null) {
      return;
    }
    const callbackData = buildCallbackData(callback.domain, callback.action, callback.arg);
    const [domain, action, arg] = callbackData.split(":");
    const toolName = `${domain}_${action}`;
    await callAntigravityTool(toolName, { arg: arg ?? "", dryRun: true }, payload.traceId);
  });
}
