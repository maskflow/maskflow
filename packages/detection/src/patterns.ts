/**
 * Regex patterns and structural validators for each PII type.
 *
 * Ported from core/src/maskflow_core/patterns.py -- keep these two files in sync.
 * Each entry maps a PIIType to a list of {regex, baseConfidence, validator}.
 * `validator(value) -> number | null` returns an adjusted confidence, or null to
 * reject the match entirely (e.g. a 16-digit number that fails the Luhn check).
 */
import { PIIType } from "./entities.js";

export type Validator = (value: string) => number | null;

export interface PatternRule {
  regex: RegExp;
  baseConfidence: number;
  validator: Validator | null;
}

const EMAIL_RE = /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b/;

const PHONE_RE = /(?<!\d)(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?!\d)/;

const SSN_DASHED_RE = /(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)/;
const SSN_PLAIN_RE = /(?<!\d)\d{9}(?!\d)/;

const CREDIT_CARD_RE = /(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)/;

const IPV4_RE = /\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b/;
const IPV6_RE = /\b(?:[A-Fa-f0-9]{1,4}:){7}[A-Fa-f0-9]{1,4}\b/;

const AWS_KEY_RE = /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/;

const API_KEY_RE =
  /\b(?:sk-ant-[A-Za-z0-9_-]{20,}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[A-Za-z0-9_-]{35})\b/;

// \w* bounded to \w{0,40} -- unbounded quantifiers flanking an alternation,
// scanned across every offset, are O(n^2) on a long word-run with no ":"/"=".
const GENERIC_SECRET_ASSIGNMENT_RE =
  /\b\w{0,40}(?:key|secret|token|password|credential)\w{0,40}\s*[:=]\s*['"]?([A-Za-z0-9_\-/+]{16,})['"]?/i;

const JWT_RE = /\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/;

const IBAN_RE = /\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b/;

// The outer {1,4} must stay bounded -- it caps backtracking on the nested
// unbounded [a-zA-Z]* inside it. Widening to {1,} risks catastrophic backtracking.
const ADDRESS_RE =
  /\b\d{1,6}\s+(?:[A-Z][a-zA-Z]*\s){1,4}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Way|Place|Pl|Terrace|Ter)\.?\b(?:,?\s+(?:Apt|Suite|Ste|Unit)\.?\s*#?\w+)?/;

function luhnIsValid(digitsStr: string): boolean {
  const digits = digitsStr.split("").map(Number);
  const parity = digits.length % 2;
  let checksum = 0;
  digits.forEach((d, i) => {
    let v = d;
    if (i % 2 === parity) {
      v *= 2;
      if (v > 9) v -= 9;
    }
    checksum += v;
  });
  return checksum % 10 === 0;
}

function validateCreditCard(value: string): number | null {
  const digits = value.replace(/[ -]/g, "");
  if (digits.length < 13 || digits.length > 19 || !/^\d+$/.test(digits)) {
    return null;
  }
  return luhnIsValid(digits) ? 0.97 : null;
}

function ibanIsValid(value: string): boolean {
  const upper = value.toUpperCase();
  const rearranged = upper.slice(4) + upper.slice(0, 4);
  let converted = "";
  for (const c of rearranged) {
    if (c >= "0" && c <= "9") {
      converted += c;
    } else if (c >= "A" && c <= "Z") {
      converted += (c.charCodeAt(0) - 55).toString();
    } else {
      return false;
    }
  }
  try {
    return BigInt(converted) % 97n === 1n;
  } catch {
    return false;
  }
}

function validateIban(value: string): number | null {
  return ibanIsValid(value) ? 0.9 : null;
}

function validateSsnDashed(value: string): number | null {
  const area = value.slice(0, 3);
  if (area === "000" || area === "666" || area.startsWith("9")) {
    return null;
  }
  return 0.95;
}

function validateSsnPlain(value: string): number | null {
  // Bare 9-digit numbers are ambiguous (order IDs, unformatted phone numbers,
  // etc.) -- start low, let context.ts decide if it's really an SSN. Still
  // apply the same area-code structural check as the dashed form, so this
  // validator can actually reject something (a no-op validator that never
  // returns null isn't a real structural check, and shouldn't be able to
  // claim `validated: true` priority during overlap resolution).
  const area = value.slice(0, 3);
  if (area === "000" || area === "666" || area.startsWith("9")) {
    return null;
  }
  return 0.35;
}

export const PATTERNS: Partial<Record<PIIType, PatternRule[]>> = {
  [PIIType.EMAIL]: [{ regex: EMAIL_RE, baseConfidence: 0.95, validator: null }],
  [PIIType.PHONE]: [{ regex: PHONE_RE, baseConfidence: 0.85, validator: null }],
  [PIIType.SSN]: [
    { regex: SSN_DASHED_RE, baseConfidence: 0.95, validator: validateSsnDashed },
    { regex: SSN_PLAIN_RE, baseConfidence: 0.35, validator: validateSsnPlain },
  ],
  [PIIType.CREDIT_CARD]: [
    { regex: CREDIT_CARD_RE, baseConfidence: 0.9, validator: validateCreditCard },
  ],
  [PIIType.IP_ADDRESS]: [
    { regex: IPV4_RE, baseConfidence: 0.75, validator: null },
    { regex: IPV6_RE, baseConfidence: 0.85, validator: null },
  ],
  [PIIType.AWS_KEY]: [{ regex: AWS_KEY_RE, baseConfidence: 0.97, validator: null }],
  [PIIType.API_KEY]: [
    { regex: API_KEY_RE, baseConfidence: 0.95, validator: null },
    { regex: GENERIC_SECRET_ASSIGNMENT_RE, baseConfidence: 0.6, validator: null },
  ],
  [PIIType.JWT]: [{ regex: JWT_RE, baseConfidence: 0.9, validator: null }],
  [PIIType.IBAN]: [{ regex: IBAN_RE, baseConfidence: 0.6, validator: validateIban }],
  [PIIType.ADDRESS]: [{ regex: ADDRESS_RE, baseConfidence: 0.7, validator: null }],
};
