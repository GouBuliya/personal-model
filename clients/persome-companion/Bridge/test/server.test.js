import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { BridgeStore } from "../store.js";
import { RuntimeForwarder } from "../server.js";

test("event receipt makes retries idempotent", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "persome-bridge-"));
  const store = new BridgeStore(path.join(root, "state.json"), () => 1_000);
  const event = { event_id: "event-1", text: "one" };
  const claim = store.claimReceipt("iphone-1", "event-1", event);
  assert.equal(claim.status, "claimed");
  assert.equal(store.claimReceipt("iphone-1", "event-1", event).status, "in_progress");
  assert.equal(
    store.completeReceipt("iphone-1", "event-1", claim.payloadHash, { id: "capture-1" }),
    true,
  );
  assert.deepEqual(store.claimReceipt("iphone-1", "event-1", event), {
    status: "accepted",
    runtimeReceipt: { id: "capture-1" },
  });
  assert.equal(
    store.claimReceipt("iphone-1", "event-1", { ...event, text: "changed" }).status,
    "conflict",
  );
});

test("runtime skip is retryable and never acknowledged", async () => {
  const forwarder = new RuntimeForwarder({
    token: "local-only-token",
    fetchImpl: async () => new Response(
      JSON.stringify({ data: { id: null, skipped: true } }),
      { status: 200, headers: { "content-type": "application/json" } },
    ),
  });

  await assert.rejects(
    forwarder.forward({ event_id: "event-1" }),
    (error) => error.statusCode === 503,
  );
});

test("runtime forwarding carries the same end-to-end idempotency key", async () => {
  let seen;
  const forwarder = new RuntimeForwarder({
    token: "local-only-token",
    fetchImpl: async (_url, init) => {
      seen = init.headers;
      return new Response(
        JSON.stringify({ data: { id: "capture-1", skipped: false } }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    },
  });

  await forwarder.forward({ event_id: "event-1" });
  assert.equal(seen["idempotency-key"], "event-1");
});
