import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { BridgeStore } from "../store.js";

const makeStore = (clock = () => Date.now()) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "persome-bridge-"));
  return new BridgeStore(path.join(root, "state.json"), clock);
};

test("pairing is one-time and stores only token hash", () => {
  const store = makeStore(() => 1_000);
  const pairing = store.createPairing();
  const device = { id: "iphone-1", platform: "ios", name: "iPhone" };
  const result = store.consumePairing({ pairingId: pairing.pairingId, code: pairing.code, device });

  assert.equal(result.ok, true);
  assert.equal(store.consumePairing({ pairingId: pairing.pairingId, code: pairing.code, device }).ok, false);
  assert.equal(store.authenticate(result.token).id, "iphone-1");
  assert.equal(JSON.stringify(store.load()).includes(result.token), false);
});

test("pairing expires and repeated guesses lock it", () => {
  let now = 1_000;
  const store = makeStore(() => now);
  const expired = store.createPairing({ ttlMs: 10 });
  now = 2_000;
  assert.equal(
    store.consumePairing({
      pairingId: expired.pairingId,
      code: expired.code,
      device: { id: "x", platform: "ios" },
    }).reason,
    "expired",
  );

  const locked = store.createPairing();
  for (let attempt = 0; attempt < 4; attempt += 1) {
    assert.equal(
      store.consumePairing({
        pairingId: locked.pairingId,
        code: "000000",
        device: { id: "x", platform: "ios" },
      }).ok,
      false,
    );
  }
  assert.equal(
    store.consumePairing({
      pairingId: locked.pairingId,
      code: "000000",
      device: { id: "x", platform: "ios" },
    }).reason,
    "locked",
  );
});

test("device sessions expire and state updates from independent store instances do not overwrite", () => {
  let now = 1_000;
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "persome-bridge-"));
  const file = path.join(root, "state.json");
  const first = new BridgeStore(file, () => now);
  const second = new BridgeStore(file, () => now);
  const one = first.createPairing();
  const two = second.createPairing();

  const paired = first.consumePairing({
    pairingId: one.pairingId,
    code: one.code,
    device: { id: "iphone-1", platform: "ios" },
    sessionTtlMs: 10,
  });
  assert.equal(paired.ok, true);
  assert.ok(first.load().pairings[two.pairingId]);
  assert.ok(second.authenticate(paired.token));
  now = 1_011;
  assert.equal(second.authenticate(paired.token), null);
});

test("revoked device can no longer authenticate", () => {
  const store = makeStore();
  const pairing = store.createPairing();
  const paired = store.consumePairing({
    pairingId: pairing.pairingId,
    code: pairing.code,
    device: { id: "iphone-1", platform: "ios" },
  });
  assert.ok(store.authenticate(paired.token));
  assert.equal(store.revoke("iphone-1"), true);
  assert.equal(store.authenticate(paired.token), null);
});

test("receipt identities cannot collide on colon-delimited ids", () => {
  const store = makeStore(() => 1_000);
  const first = store.claimReceipt("a:b", "c", { value: 1 });
  const second = store.claimReceipt("a", "b:c", { value: 2 });
  assert.equal(first.status, "claimed");
  assert.equal(second.status, "claimed");
  assert.equal(Object.keys(store.load().receipts).length, 2);
});
