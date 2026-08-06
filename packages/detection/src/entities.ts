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
}
