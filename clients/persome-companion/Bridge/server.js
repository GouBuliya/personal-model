import fs from "node:fs";
import https from "node:https";

const MAX_BODY_BYTES = 600 * 1024;

export function createBridgeServer({ store, certPath, keyPath, runtime }) {
  return https.createServer(
    { cert: fs.readFileSync(certPath), key: fs.readFileSync(keyPath), minVersion: "TLSv1.3" },
    async (request, response) => {
      try {
        if (request.method === "GET" && request.url === "/health") {
          return json(response, 200, { ok: true });
        }
        if (request.method === "POST" && request.url === "/v1/pair") {
          const body = await readJSON(request);
          if (!validDevice(body.device) || typeof body.pairing_id !== "string") {
            return json(response, 400, { error: "invalid pairing payload" });
          }
          const result = store.consumePairing({
            pairingId: body.pairing_id,
            code: body.code,
            device: body.device,
          });
          if (!result.ok) return json(response, 401, { error: `pairing ${result.reason}` });
          return json(response, 201, {
            session_token: result.token,
            session_expires_at: result.expiresAt,
            device_id: body.device.id,
          });
        }
        if (request.method === "DELETE" && request.url === "/v1/session") {
          const device = store.authenticate(bearer(request.headers.authorization));
          if (!device) return json(response, 401, { error: "invalid device session" });
          store.revoke(device.id);
          response.writeHead(204, { "cache-control": "no-store" });
          return response.end();
        }
        if (request.method === "POST" && request.url === "/v1/events") {
          const device = store.authenticate(bearer(request.headers.authorization));
          if (!device) return json(response, 401, { error: "invalid device session" });
          const body = await readJSON(request);
          if (body?.device?.id !== device.id || typeof body.event_id !== "string") {
            return json(response, 403, { error: "event device does not match session" });
          }
          const idempotencyKey = request.headers["idempotency-key"];
          if (idempotencyKey !== body.event_id) {
            return json(response, 400, { error: "idempotency key must equal event_id" });
          }
          const claim = store.claimReceipt(device.id, body.event_id, body);
          if (claim.status === "conflict") {
            return json(response, 409, { error: "event_id was already used for another payload" });
          }
          if (claim.status === "in_progress") {
            return json(response, 409, { error: "event is already being forwarded; retry later" });
          }
          if (claim.status === "accepted") {
            return json(response, 200, {
              accepted: true,
              deduped: true,
              runtime: claim.runtimeReceipt,
            });
          }
          let runtimeReceipt;
          try {
            runtimeReceipt = await runtime.forward(body);
          } catch (error) {
            store.releaseReceipt(device.id, body.event_id, claim.payloadHash);
            throw error;
          }
          if (!store.completeReceipt(device.id, body.event_id, claim.payloadHash, runtimeReceipt)) {
            const error = new Error("event receipt claim was lost");
            error.statusCode = 503;
            throw error;
          }
          return json(response, 202, { accepted: true, deduped: false, runtime: runtimeReceipt });
        }
        return json(response, 404, { error: "not found" });
      } catch (error) {
        const status = error.statusCode ?? 500;
        return json(response, status, { error: status === 500 ? "bridge error" : error.message });
      }
    },
  );
}

export class RuntimeForwarder {
  constructor({ baseURL = "http://127.0.0.1:8742", token, fetchImpl = fetch }) {
    this.baseURL = baseURL.replace(/\/$/, "");
    this.token = token;
    this.fetchImpl = fetchImpl;
  }

  async forward(event) {
    const response = await this.fetchImpl(`${this.baseURL}/mobile/events/ingest`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${this.token}`,
        "idempotency-key": event.event_id,
      },
      body: JSON.stringify(event),
    });
    if (!response.ok) {
      const error = new Error(`runtime rejected event (${response.status})`);
      error.statusCode = 502;
      throw error;
    }
    const receipt = (await response.json()).data;
    if (receipt?.skipped) {
      const error = new Error("runtime temporarily skipped event");
      error.statusCode = 503;
      throw error;
    }
    return receipt;
  }
}

async function readJSON(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) {
      const error = new Error("request body too large");
      error.statusCode = 413;
      throw error;
    }
    chunks.push(chunk);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString("utf8"));
  } catch {
    const error = new Error("invalid JSON");
    error.statusCode = 400;
    throw error;
  }
}

function validDevice(device) {
  return (
    device &&
    typeof device.id === "string" &&
    device.id.trim().length >= 1 &&
    device.id.length <= 128 &&
    ["ios", "android"].includes(device.platform) &&
    (device.name === undefined || device.name === null ||
      (typeof device.name === "string" && device.name.length <= 128))
  );
}

function bearer(value) {
  return typeof value === "string" && value.startsWith("Bearer ") ? value.slice(7) : null;
}

function json(response, status, body) {
  response.writeHead(status, {
    "content-type": "application/json",
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
  });
  response.end(JSON.stringify(body));
}
