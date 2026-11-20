// Stateless free-tier fallback for the fixed public synthetic receipt.

const MAX_REQUEST_BYTES = 256;
const FIXTURE = "synthetic-canonical-json-v1";
const OPERATION = "canonical_json_sha256";
const SCOPE = "synthetic_public";
const OUTPUT = '{"a":["β",{"x":null,"y":true}],"m":0,"z":3}';
const encoder = new TextEncoder();
const decoder = new TextDecoder("utf-8", {fatal: true, ignoreBOM: true});

function response(status, value, extraHeaders = {}) {
  return new Response(JSON.stringify(value) + "\n", {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...extraHeaders,
    },
  });
}

async function boundedBody(request) {
  const length = request.headers.get("Content-Length");
  if (length !== null && (!/^\d{1,9}$/.test(length) || Number(length) > MAX_REQUEST_BYTES)) {
    return {error: 413};
  }
  const reader = request.body?.getReader();
  if (!reader) return {error: 400};

  const buffer = new Uint8Array(MAX_REQUEST_BYTES);
  let offset = 0;
  try {
    // Each normal chunk contributes at least one byte. Limit empty-chunk traffic too.
    for (let reads = 0; reads <= MAX_REQUEST_BYTES; reads += 1) {
      const {value, done} = await reader.read();
      if (done) return {text: decoder.decode(buffer.subarray(0, offset))};
      if (value.byteLength > MAX_REQUEST_BYTES - offset) break;
      buffer.set(value, offset);
      offset += value.byteLength;
    }
    void reader.cancel().catch(() => {});
    return {error: 413};
  } catch {
    return {error: 400};
  } finally {
    reader.releaseLock();
  }
}

function requestId(text) {
  let request;
  try {
    request = JSON.parse(text);
  } catch {
    return null;
  }
  const id = request?.request_id;
  if (typeof id !== "string" || id.length !== 32 || !/^[0-9a-f]{32}$/.test(id)) return null;
  // The exact canonical bytes also reject repeated, reordered, and extra fields.
  const canonical = JSON.stringify({
    data_scope: SCOPE,
    fixture: FIXTURE,
    operation: OPERATION,
    request_id: id,
    schema: "cloud-work-request/v1",
  });
  return text === canonical ? id : null;
}

async function digest(bytes) {
  const sum = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  return Array.from(sum, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname !== "/v1/transform" || url.search) return response(404, {error: "route_not_found"});
    if (request.method !== "POST") return response(405, {error: "post_required"}, {Allow: "POST"});
    if (request.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase() !== "application/json"
        || ![null, "identity"].includes(request.headers.get("Content-Encoding"))) {
      return response(415, {error: "uncompressed_json_required"});
    }

    const body = await boundedBody(request);
    if (body.error === 413) return response(413, {error: "body_limit_exceeded"});
    const id = body.error ? null : requestId(body.text);
    if (id === null) return response(400, {error: "exact_public_request_required"});

    const output = encoder.encode(OUTPUT);
    const [boundRequest, boundOutput] = await Promise.all([digest(encoder.encode(body.text)), digest(output)]);
    return response(200, {
      data_scope: SCOPE,
      executor: "cloudflare-workers-webcrypto-v1",
      fixture: FIXTURE,
      inference: false,
      operation: OPERATION,
      output: {bytes: output.byteLength, canonical_json: OUTPUT, sha256: boundOutput},
      request_id: id,
      request_sha256: boundRequest,
      schema: "cloud-work-receipt/v1",
    });
  },
};
