import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const SESSION_TTL_MS = 90 * 24 * 60 * 60_000;
const RECEIPT_TTL_MS = 30 * 24 * 60 * 60_000;
const RECEIPT_LEASE_MS = 30_000;
const RECEIPT_LIMIT = 10_000;
const LOCK_WAIT_MS = 2_000;
const LOCK_STALE_MS = 30_000;

const emptyState = () => ({ version: 2, pairings: {}, devices: {}, receipts: {} });

export class BridgeStore {
  constructor(filePath, clock = () => Date.now()) {
    this.filePath = filePath;
    this.lockPath = `${filePath}.lock`;
    this.clock = clock;
  }

  load() {
    try {
      const parsed = JSON.parse(fs.readFileSync(this.filePath, "utf8"));
      return { ...emptyState(), ...parsed, version: 2 };
    } catch (error) {
      if (error.code === "ENOENT") return emptyState();
      throw error;
    }
  }

  save(state) {
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true, mode: 0o700 });
    const temp = `${this.filePath}.${process.pid}.${crypto.randomUUID()}.tmp`;
    let descriptor;
    try {
      descriptor = fs.openSync(temp, "wx", 0o600);
      fs.writeFileSync(descriptor, `${JSON.stringify(state, null, 2)}\n`);
      fs.fsyncSync(descriptor);
      fs.closeSync(descriptor);
      descriptor = undefined;
      fs.renameSync(temp, this.filePath);
      fs.chmodSync(this.filePath, 0o600);
      const directory = fs.openSync(path.dirname(this.filePath), "r");
      try {
        fs.fsyncSync(directory);
      } finally {
        fs.closeSync(directory);
      }
    } finally {
      if (descriptor !== undefined) fs.closeSync(descriptor);
      try {
        fs.unlinkSync(temp);
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
      }
    }
  }

  createPairing({ ttlMs = 5 * 60_000 } = {}) {
    return this.#update((state) => {
      this.#prune(state);
      const pairingId = crypto.randomUUID();
      const code = crypto.randomInt(100_000, 1_000_000).toString();
      state.pairings[pairingId] = {
        codeHash: digest(code),
        expiresAt: this.clock() + ttlMs,
        attempts: 0,
      };
      return { pairingId, code, expiresAt: state.pairings[pairingId].expiresAt };
    });
  }

  consumePairing({ pairingId, code, device, sessionTtlMs = SESSION_TTL_MS }) {
    return this.#update((state) => {
      this.#prune(state);
      const pairing = state.pairings[pairingId];
      if (!pairing) return { ok: false, reason: "expired" };
      if (pairing.expiresAt <= this.clock()) {
        delete state.pairings[pairingId];
        return { ok: false, reason: "expired" };
      }
      if (!safeEqual(pairing.codeHash, digest(code))) {
        pairing.attempts += 1;
        if (pairing.attempts >= 5) {
          delete state.pairings[pairingId];
          return { ok: false, reason: "locked" };
        }
        return { ok: false, reason: "invalid" };
      }

      delete state.pairings[pairingId];
      const token = crypto.randomBytes(32).toString("base64url");
      const expiresAt = this.clock() + sessionTtlMs;
      state.devices[device.id] = {
        id: device.id,
        platform: device.platform,
        name: device.name ?? null,
        tokenHash: digest(token),
        pairedAt: new Date(this.clock()).toISOString(),
        expiresAt,
        lastSeenAt: null,
        revokedAt: null,
      };
      return { ok: true, token, expiresAt };
    });
  }

  authenticate(token) {
    if (!token) return null;
    const state = this.load();
    const tokenHash = digest(token);
    for (const device of Object.values(state.devices)) {
      const expiresAt = Number(device.expiresAt ?? 0);
      if (!device.revokedAt && expiresAt > this.clock() && safeEqual(device.tokenHash, tokenHash)) {
        return device;
      }
    }
    return null;
  }

  claimReceipt(deviceId, eventId, payload) {
    const payloadHash = digest(stableJSON(payload));
    return this.#update((state) => {
      this.#prune(state);
      const key = receiptKey(deviceId, eventId);
      const existing = state.receipts[key];
      if (existing) {
        if (
          existing.deviceId !== deviceId ||
          existing.eventId !== eventId ||
          existing.payloadHash !== payloadHash
        ) {
          return { status: "conflict" };
        }
        if (existing.status === "accepted") {
          return { status: "accepted", runtimeReceipt: existing.runtimeReceipt };
        }
        if (Number(existing.leaseUntil ?? 0) > this.clock()) {
          return { status: "in_progress" };
        }
        existing.leaseUntil = this.clock() + RECEIPT_LEASE_MS;
        existing.updatedAt = new Date(this.clock()).toISOString();
        return { status: "claimed", payloadHash };
      }
      state.receipts[key] = {
        deviceId,
        eventId,
        payloadHash,
        status: "pending",
        leaseUntil: this.clock() + RECEIPT_LEASE_MS,
        createdAt: new Date(this.clock()).toISOString(),
        updatedAt: new Date(this.clock()).toISOString(),
      };
      return { status: "claimed", payloadHash };
    });
  }

  completeReceipt(deviceId, eventId, payloadHash, runtimeReceipt) {
    return this.#update((state) => {
      const receipt = state.receipts[receiptKey(deviceId, eventId)];
      if (
        !receipt ||
        receipt.deviceId !== deviceId ||
        receipt.eventId !== eventId ||
        receipt.payloadHash !== payloadHash
      ) {
        return false;
      }
      receipt.status = "accepted";
      receipt.runtimeReceipt = runtimeReceipt;
      receipt.acceptedAt = new Date(this.clock()).toISOString();
      receipt.updatedAt = receipt.acceptedAt;
      delete receipt.leaseUntil;
      if (state.devices[deviceId]) state.devices[deviceId].lastSeenAt = receipt.acceptedAt;
      this.#prune(state);
      return true;
    });
  }

  releaseReceipt(deviceId, eventId, payloadHash) {
    return this.#update((state) => {
      const key = receiptKey(deviceId, eventId);
      const receipt = state.receipts[key];
      if (receipt?.status !== "pending" || receipt.payloadHash !== payloadHash) return false;
      receipt.leaseUntil = 0;
      receipt.updatedAt = new Date(this.clock()).toISOString();
      return true;
    });
  }

  listDevices() {
    return Object.values(this.load().devices).map(({ tokenHash, ...device }) => device);
  }

  revoke(deviceId) {
    return this.#update((state) => {
      if (!state.devices[deviceId]) return false;
      state.devices[deviceId].revokedAt = new Date(this.clock()).toISOString();
      return true;
    });
  }

  #update(mutator) {
    const release = this.#acquireLock();
    try {
      const state = this.load();
      const result = mutator(state);
      this.save(state);
      return result;
    } finally {
      release();
    }
  }

  #prune(state) {
    const now = this.clock();
    for (const [pairingId, pairing] of Object.entries(state.pairings)) {
      if (Number(pairing.expiresAt ?? 0) <= now) delete state.pairings[pairingId];
    }
    for (const [key, receipt] of Object.entries(state.receipts)) {
      const acceptedAt = Date.parse(receipt.acceptedAt ?? "");
      const updatedAt = Date.parse(receipt.updatedAt ?? receipt.createdAt ?? "");
      if (
        (receipt.status === "accepted" && acceptedAt < now - RECEIPT_TTL_MS) ||
        (receipt.status !== "accepted" && updatedAt < now - RECEIPT_LEASE_MS * 10)
      ) {
        delete state.receipts[key];
      }
    }
    const accepted = Object.entries(state.receipts)
      .filter(([, receipt]) => receipt.status === "accepted")
      .sort((left, right) => Date.parse(left[1].acceptedAt) - Date.parse(right[1].acceptedAt));
    for (const [key] of accepted.slice(0, Math.max(0, accepted.length - RECEIPT_LIMIT))) {
      delete state.receipts[key];
    }
  }

  #acquireLock() {
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true, mode: 0o700 });
    const deadline = Date.now() + LOCK_WAIT_MS;
    while (true) {
      try {
        fs.mkdirSync(this.lockPath, { mode: 0o700 });
        break;
      } catch (error) {
        if (error.code !== "EEXIST") throw error;
        try {
          const stat = fs.lstatSync(this.lockPath);
          if (Date.now() - stat.mtimeMs > LOCK_STALE_MS) {
            fs.rmSync(this.lockPath, { recursive: true, force: true });
            continue;
          }
        } catch (statError) {
          if (statError.code === "ENOENT") continue;
          throw statError;
        }
        if (Date.now() >= deadline) throw new Error("bridge state lock timed out");
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 10);
      }
    }
    return () => {
      try {
        fs.rmdirSync(this.lockPath);
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
      }
    };
  }
}

const digest = (value) => crypto.createHash("sha256").update(String(value)).digest("hex");
const receiptKey = (deviceId, eventId) => digest(stableJSON([deviceId, eventId]));

function stableJSON(value) {
  if (Array.isArray(value)) return `[${value.map(stableJSON).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableJSON(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function safeEqual(left, right) {
  const a = Buffer.from(String(left));
  const b = Buffer.from(String(right));
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}
