export enum PIIType {
  EMAIL = "EMAIL",
  PHONE = "PHONE",
  SSN = "SSN",
  CREDIT_CARD = "CREDIT_CARD",
  IP_ADDRESS = "IP_ADDRESS",
  AWS_KEY = "AWS_KEY",
  API_KEY = "API_KEY",
  JWT = "JWT",
  IBAN = "IBAN",
  ADDRESS = "ADDRESS",
}

export interface Finding {
  type: PIIType;
  value: string;
  start: number;
  end: number;
  confidence: number;
  // True only when a structural validator ran and confirmed the match
  // (checksum-valid Luhn card, mod-97 IBAN, ...). Used to give validated
  // spans priority over unvalidated ones during overlap resolution.
  validated: boolean;
}
