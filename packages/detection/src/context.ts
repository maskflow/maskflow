/**
 * Keyword-proximity confidence boosting.
 *
 * Structural matches (email, credit card w/ Luhn, AWS keys, ...) are already
 * high-confidence on their own. Ambiguous matches (a bare 9-digit number, a
 * street-shaped line of text) need a nearby keyword to be trusted.
 */
import { PIIType } from "./entities";

const WINDOW = 40;

const CONTEXT_KEYWORDS: Partial<Record<PIIType, readonly string[]>> = {
  [PIIType.SSN]: ["ssn", "social security"],
  [PIIType.ADDRESS]: ["address", "lives at", "located at", "ship to", "mailing"],
  [PIIType.API_KEY]: ["api key", "apikey", "secret", "token", "credential"],
  [PIIType.PHONE]: ["phone", "call", "tel", "mobile", "cell", "contact"],
  [PIIType.CREDIT_CARD]: ["card number", "credit card", "visa", "mastercard", "cc#"],
};

const BOOST = 0.4;
const MAX_CONFIDENCE = 0.99;

export function applyContextBoost(
  text: string,
  start: number,
  end: number,
  piiType: PIIType,
  baseConfidence: number,
): number {
  const keywords = CONTEXT_KEYWORDS[piiType];
  if (!keywords) {
    return baseConfidence;
  }

  const windowStart = Math.max(0, start - WINDOW);
  const windowEnd = Math.min(text.length, end + WINDOW);
  const nearby =
    text.slice(windowStart, start).toLowerCase() + " " + text.slice(end, windowEnd).toLowerCase();

  if (keywords.some((keyword) => nearby.includes(keyword))) {
    return Math.min(MAX_CONFIDENCE, baseConfidence + BOOST);
  }
  return baseConfidence;
}
