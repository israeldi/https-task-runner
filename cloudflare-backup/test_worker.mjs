import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import test from "node:test";
import worker from "./worker.mjs";

const URL = "https://synthetic-backup.example.invalid/v1/transform";
const ID = "0123456789abcdef0123456789abcdef";
const REQUEST = '{"data_scope":"synthetic_public","fixture":"synthetic-canonical-json-v1","operation":"canonical_json_sha256","request_id":"'
  + ID + '","schema":"cloud-work-request/v1"}';
const EXPECTED = {
  data_scope: "synthetic_public",
  executor: "cloudflare-workers-webcrypto-v1",
  fixture: "synthetic-canonical-json-v1",
  inference: false,
  operation: "canonical_json_sha256",
  output: {
    bytes: 44,
    canonical_json: '{"a":["β",{"x":null,"y":true}],"m":0,"z":3}',
    sha256: "f8da18c39cbe396c3c5e481053a39d58927926ced5404f072d2d166d74bde696",
  },
  request_id: ID,
  request_sha256: "c84a6ce279f75a31e505e42f7f9ffb4a7998efa7e5cfc24c1c1a400353df638f",
  schema: "cloud-work-receipt/v1",
};

function post(body, options = {}) {
  return new Request(URL, {
    method: "POST", headers: {"Content-Type": "application/json"}, body, ...options,
  });
}

test("fixed Cloudflare receipt bytes match the independent reference", async () => {
  const reply = await worker.fetch(post(REQUEST));
  assert.equal(reply.status, 200);
  assert.equal(reply.headers.get("Cache-Control"), "no-store");
  assert.equal(await reply.text(), JSON.stringify(EXPECTED) + "\n");
});

test("a different opaque ID binds a new request and the same output", async () => {
  const request = REQUEST.replace(ID, "0".repeat(32));
  const reply = await worker.fetch(post(request));
  assert.equal(reply.status, 200);
  const receipt = await reply.json();
  assert.deepEqual(receipt.output, EXPECTED.output);
  assert.equal(receipt.request_sha256, createHash("sha256").update(request).digest("hex"));
  assert.notEqual(receipt.request_sha256, EXPECTED.request_sha256);
});

test("only one exact POST route can produce a receipt", async () => {
  const invalid = await worker.fetch(new Request(URL + "?url=https://example.invalid/"));
  assert.equal(invalid.status, 404);
  const method = await worker.fetch(new Request(URL));
  assert.equal(method.status, 405);
  assert.equal(method.headers.get("Allow"), "POST");
});

test("private, malformed, noncanonical, duplicate, and extra data are refused", async () => {
  const bad = [
    REQUEST.replace("synthetic_public", "private"),
    REQUEST.replace("canonical_json_sha256", "arbitrary"),
    REQUEST.replace(ID, ID.toUpperCase()),
    REQUEST.replace(ID, "x".repeat(32)),
    REQUEST.replace(ID, "a".repeat(31)),
    REQUEST.replace(ID, ID + "\\n"),
    REQUEST + "\n",
    '{ "schema": "cloud-work-request/v1" }',
    REQUEST.slice(0, -1) + ',"schema":"cloud-work-request/v1"}',
    REQUEST.slice(0, -1) + ',"url":"https://example.invalid/"}',
    "\uFEFF" + REQUEST,
    Uint8Array.of(0xff),
  ];
  for (const body of bad) {
    const reply = await worker.fetch(post(body));
    assert.equal(reply.status, 400);
    assert.deepEqual(await reply.json(), {error: "exact_public_request_required"});
  }
});

test("the size cap applies with and without a content-length header", async () => {
  const supplied = await worker.fetch(post(REQUEST, {
    headers: {"Content-Type": "application/json", "Content-Length": "257"},
  }));
  assert.equal(supplied.status, 413);
  const streamed = await worker.fetch(post("a".repeat(257)));
  assert.equal(streamed.status, 413);
});

test("encoded or non-JSON uploads are refused", async () => {
  for (const headers of [
    {"Content-Type": "text/plain"},
    {"Content-Type": "application/json", "Content-Encoding": "gzip"},
  ]) {
    assert.equal((await worker.fetch(post(REQUEST, {headers}))).status, 415);
  }
});

test("compute completes without any outbound fetch", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = () => {
    throw new Error("Unexpected outbound request");
  };
  try {
    assert.equal((await worker.fetch(post(REQUEST))).status, 200);
  } finally {
    globalThis.fetch = original;
  }
});
