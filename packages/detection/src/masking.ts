/** Pure, stateless mask/unmask. No storage -- the caller owns persisting the mapping.
 * Ported from core/src/maskflow_core/masking.py. */
import { DEFAULT_MIN_CONFIDENCE, detect } from "./detection";

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

  for (const finding of findings) {
    counters[finding.type] = (counters[finding.type] ?? 0) + 1;
    const token = `<${finding.type}_${counters[finding.type]}>`;
    mapping[token] = finding.value;
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
