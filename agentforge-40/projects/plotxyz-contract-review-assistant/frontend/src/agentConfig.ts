export type FieldType = "text" | "textarea" | "number" | "checkbox";

export interface AgentField {
  name: string;
  label: string;
  type: FieldType;
  rows?: number;
  placeholder?: string;
}

export interface AgentConfig {
  slug: string;
  title: string;
  tagline: string;
  purpose: string;
  accent: string;
  features: string[];
  limitations: string[];
  fields: AgentField[];
  sample: Record<string, string | number | boolean>;
  repo: string;
}

export const agent: AgentConfig = {
  "slug": "plotxyz-contract-review-assistant",
  "title": "Contract Review",
  "tagline": "Surface the clauses a human should read first.",
  "purpose": "Detects common contract clause categories and flags potentially one-sided language for human review. It does not provide legal advice.",
  "accent": "#f59e0b",
  "features": [
    "Clause-category detection",
    "One-sided language flags",
    "Excerpt table for review"
  ],
  "limitations": [
    "Keyword-based analysis is not legal advice.",
    "Absence of a clause in an excerpt does not prove it is missing."
  ],
  "fields": [
    {
      "name": "text",
      "label": "Contract excerpt",
      "type": "textarea",
      "rows": 10,
      "placeholder": ""
    }
  ],
  "sample": {
    "text": "The Client shall pay the fee within 30 days. This Agreement automatically renews for successive one-year terms unless terminated with 60 days notice. The Provider's liability is unlimited. Confidential information must be protected."
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-contract-review-assistant"
};
