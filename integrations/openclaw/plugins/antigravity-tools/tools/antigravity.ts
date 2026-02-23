export interface JsonPrimitive {
  value: string | number | boolean | null;
}

export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface AntigravityResponse {
  success: boolean;
  data?: { [key: string]: JsonValue };
  error?: { message: string; code?: string };
  trace_id: string;
  content?: { type: "text"; text: string }[];
}

export async function callAntigravityTool(
  toolName: string,
  params: { [key: string]: JsonValue },
  traceId: string,
): Promise<AntigravityResponse> {
  const endpoint = process.env.ANTIGRAVITY_URL;
  if (endpoint === undefined || endpoint.trim().length === 0) {
    throw new Error("ANTIGRAVITY_URL not configured");
  }

  const response = await fetch(`${endpoint}/api/tools/${toolName}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Trace-Id": traceId,
    },
    body: JSON.stringify(params),
  });

  const payload = (await response.json()) as AntigravityResponse;
  if (!response.ok) {
    const message = payload.error?.message ?? `tool bridge failed status=${response.status}`;
    throw new Error(`${message} trace_id=${payload.trace_id}`);
  }
  return payload;
}
