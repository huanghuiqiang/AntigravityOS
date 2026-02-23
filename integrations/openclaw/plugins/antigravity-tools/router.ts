export interface CallbackRoute {
  domain: string;
  action: string;
  arg?: string;
}

export interface CallbackPayload {
  text: string;
  traceId: string;
}

const CALLBACK_PREFIX = "callback_data: ";

export function parseCallback(input: string): string | null {
  const trimmed = input.trim();
  if (!trimmed.startsWith(CALLBACK_PREFIX)) {
    return null;
  }
  const value = trimmed.slice(CALLBACK_PREFIX.length).trim();
  return value.length > 0 ? value : null;
}

export function buildCallbackData(domain: string, action: string, arg?: string): string {
  const values = [domain, action];
  if (arg !== undefined && arg.length > 0) {
    values.push(arg);
  }
  const joined = values.join(":");
  const length = Buffer.byteLength(joined, "utf8");
  if (length > 64) {
    throw new Error(`callback_data too long: ${length}`);
  }
  return joined;
}

export function routeTelegramCallback(input: string): CallbackRoute | null {
  const callback = parseCallback(input);
  if (callback === null) {
    return null;
  }
  const parts = callback.split(":");
  if (parts.length < 2) {
    throw new Error(`invalid callback_data format: ${callback}`);
  }

  const domain = parts[0];
  const action = parts[1];
  const arg = parts.length > 2 ? parts.slice(2).join(":") : undefined;

  if (domain.length === 0 || action.length === 0) {
    throw new Error(`invalid callback_data format: ${callback}`);
  }

  return { domain, action, arg };
}
