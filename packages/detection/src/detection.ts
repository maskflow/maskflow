/** Orchestrates the regex pass into one deduplicated finding list. Ported from
 * core/src/maskflow_core/detection.py -- the NER pass (person names, dates) has
 * no browser-side equivalent and isn't part of this package. */
import { applyContextBoost } from "./context";
import { Finding, PIIType } from "./entities";
import { PATTERNS } from "./patterns";

export const DEFAULT_MIN_CONFIDENCE = 0.5;

function execAll(rule: { regex: RegExp }, text: string): RegExpExecArray[] {
  const flags = rule.regex.flags.replace(/[gd]/g, "") + "gd";
  const regex = new RegExp(rule.regex.source, flags);
  const matches: RegExpExecArray[] = [];
  let match: RegExpExecArray | null;
  while ((match = regex.exec(text)) !== null) {
    matches.push(match);
    if (match[0].length === 0) {
      regex.lastIndex += 1;
    }
  }
  return matches;
}

function regexPass(text: string): Finding[] {
  const candidates: Finding[] = [];

  for (const [piiType, rules] of Object.entries(PATTERNS) as [PIIType, typeof PATTERNS[PIIType]][]) {
    for (const rule of rules!) {
      for (const match of execAll(rule, text)) {
        let start: number;
        let end: number;
        let value: string;

        const indices = (match as RegExpExecArray & { indices?: Array<[number, number] | undefined> })
          .indices;

        if (match.length > 1 && match[1] !== undefined && indices?.[1]) {
          [start, end] = indices[1];
          value = match[1];
        } else {
          start = match.index;
          end = start + match[0].length;
          value = match[0];
        }

        let confidence = rule.baseConfidence;
        if (rule.validator) {
          const adjusted = rule.validator(value);
          if (adjusted === null) continue;
          confidence = adjusted;
        }

        confidence = applyContextBoost(text, start, end, piiType, confidence);
        candidates.push({
          type: piiType,
          value,
          start,
          end,
          confidence: Math.round(confidence * 100) / 100,
        });
      }
    }
  }

  return candidates;
}

function spansOverlap(a: Finding, b: Finding): boolean {
  return a.start < b.end && b.start < a.end;
}

function mergeOverlaps(candidates: Finding[]): Finding[] {
  const accepted: Finding[] = [];
  const sorted = [...candidates].sort((a, b) => b.confidence - a.confidence);
  for (const finding of sorted) {
    if (!accepted.some((kept) => spansOverlap(finding, kept))) {
      accepted.push(finding);
    }
  }
  return accepted.sort((a, b) => a.start - b.start);
}

export function detect(text: string, minConfidence: number = DEFAULT_MIN_CONFIDENCE): Finding[] {
  const candidates = regexPass(text);
  const merged = mergeOverlaps(candidates);
  return merged.filter((f) => f.confidence >= minConfidence);
}
