/** Pure, stateless mask/unmask. No storage -- the caller owns persisting the mapping.
 * Ported from core/src/maskflow_core/masking.py. */
import { DEFAULT_MIN_CONFIDENCE, detect } from "./detection.js";

// Matches both plain (<EMAIL_1>) and nonce-suffixed (<EMAIL_1_a4f9>) tokens, so
// input text that already contains placeholder-lookalike substrings is detected
// and never collided with.
const RESERVED_TOKEN_RE = /<[A-Z_]+_\d+(?:_[0-9a-f]+)?>/g;

function randomNonce(): string {
  return Math.floor(Math.random() * 0x10000)
    .toString(16)
    .padStart(4, "0");
}

export interface MaskResult {
  maskedText: string;
  mapping: Record<string, string>;
}

export function mask(text: string, minConfidence: number = DEFAULT_MIN_CONFIDENCE): MaskResult {
  const findings = detect(text, minConfidence);

  const mapping: Record<string, string> = {};
  const counters: Record<string, number> = {};
  const pieces: string[] = [];
  let cursor = 0;
  // Placeholder-lookalike text already present in the input (e.g. someone's
  // prompt literally contains "<EMAIL_1>") must never collide with a token
  // we assign -- track everything already claimed, real or lookalike.
  const reserved = new Set(text.match(RESERVED_TOKEN_RE) ?? []);

  for (const finding of findings) {
    counters[finding.type] = (counters[finding.type] ?? 0) + 1;
    let token = `<${finding.type}_${counters[finding.type]}>`;
    while (reserved.has(token)) {
      token = `<${finding.type}_${counters[finding.type]}_${randomNonce()}>`;
    }
    mapping[token] = finding.value;
    reserved.add(token);
    pieces.push(text.slice(cursor, finding.start));
    pieces.push(token);
    cursor = finding.end;
  }

  pieces.push(text.slice(cursor));
  return { maskedText: pieces.join(""), mapping };
}

export function unmask(maskedText: string, mapping: Record<string, string>): string {
  let result = maskedText;
  for (const [token, original] of Object.entries(mapping)) {
    result = result.split(token).join(original);
  }
  return result;
}
