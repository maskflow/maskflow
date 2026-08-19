import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { detect, mask, PIIType, unmask } from "../src/index";

const __dirname = dirname(fileURLToPath(import.meta.url));

interface FixtureSample {
  text: string;
  expected: { type: string; value: string }[];
}

interface Fixtures {
  positive: FixtureSample[];
  negative: string[];
}

const fixtures: Fixtures = JSON.parse(readFileSync(join(__dirname, "fixtures.json"), "utf-8"));

describe("detect() accuracy against the shared core fixtures", () => {
  it("finds every expected entity in each positive sample (recall)", () => {
    let checked = 0;
    let missed = 0;
    const misses: string[] = [];

    for (const sample of fixtures.positive) {
      const findings = detect(sample.text);
      for (const exp of sample.expected) {
        checked += 1;
        const found = findings.some((f) => f.type === exp.type && f.value === exp.value);
        if (!found) {
          missed += 1;
          misses.push(`${exp.type} "${exp.value}" in: ${sample.text}`);
        }
      }
    }

    const accuracy = (checked - missed) / checked;
    expect(accuracy, `misses:\n${misses.join("\n")}`).toBeGreaterThanOrEqual(0.95);
  });

  it("produces zero findings on PII-free text (precision)", () => {
    for (const text of fixtures.negative) {
      expect(detect(text), `false positive on: ${text}`).toEqual([]);
    }
  });
});

describe("mask()/unmask()", () => {
  it("replaces PII with tokens and round-trips exactly", () => {
    const text = "Email me at alice@example.com or call 415-555-0132.";
    const result = mask(text);

    expect(result.maskedText).not.toContain("alice@example.com");
    expect(result.maskedText).not.toContain("415-555-0132");
    expect(result.maskedText).toContain("<EMAIL_1>");
    expect(result.maskedText).toContain("<PHONE_1>");
    expect(unmask(result.maskedText, result.mapping)).toBe(text);
  });

  it("is idempotent on clean text", () => {
    const text = "This sentence has no PII in it at all.";
    const result = mask(text);
    expect(result.maskedText).toBe(text);
    expect(result.mapping).toEqual({});
  });

  it("numbers tokens of the same type sequentially", () => {
    const result = mask("Contact alice@example.com or bob@example.com.");
    expect(result.mapping["<EMAIL_1>"]).toBe("alice@example.com");
    expect(result.mapping["<EMAIL_2>"]).toBe("bob@example.com");
  });

  it("round-trips exactly with emoji adjacent to PII", () => {
    const text = "📧 Email me at alice@example.com 👍 or call 415-555-0132 📞 thanks!";
    const result = mask(text);
    expect(unmask(result.maskedText, result.mapping)).toBe(text);
  });

  it("round-trips exactly with RTL text surrounding PII", () => {
    const text = "مرحبا بك، راسلني على alice@example.com من فضلك";
    const result = mask(text);
    expect(unmask(result.maskedText, result.mapping)).toBe(text);
  });

  it("round-trips exactly with zero-width characters near PII", () => {
    const zwsp = "​";
    const zwj = "‍";
    const text = `Contact${zwsp} me at alice@example.com${zwj} please reach out`;
    const result = mask(text);
    expect(unmask(result.maskedText, result.mapping)).toBe(text);
  });

  it("round-trips exactly with mixed unicode and multiple entities", () => {
    const zwsp = "​";
    const zwj = "‍";
    const text = `👋 مرحبا${zwsp} Email: alice@example.com${zwj} Phone: 415-555-0132 🎉`;
    const result = mask(text);
    expect(unmask(result.maskedText, result.mapping)).toBe(text);
  });

  it("avoids colliding with placeholder-lookalike text already in the input", () => {
    const text = "Please keep the literal token <EMAIL_1> as-is. Contact bob@example.com.";
    const result = mask(text);

    expect(result.mapping["<EMAIL_1>"]).toBeUndefined();
    expect(result.maskedText).not.toContain("bob@example.com");
    expect(unmask(result.maskedText, result.mapping)).toBe(text);
  });
});

describe("PIIType", () => {
  it("does not include NER-only types", () => {
    expect(Object.values(PIIType)).not.toContain("PERSON_NAME");
    expect(Object.values(PIIType)).not.toContain("DATE_OF_BIRTH");
  });
});
