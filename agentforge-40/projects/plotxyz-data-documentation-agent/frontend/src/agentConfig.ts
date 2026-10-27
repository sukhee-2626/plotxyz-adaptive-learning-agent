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
  "slug": "plotxyz-data-documentation-agent",
  "title": "Data Documentation",
  "tagline": "A data dictionary that starts itself.",
  "purpose": "Generates a column-level data dictionary from a declared schema, with optional sample statistics and name-derived descriptions.",
  "accent": "#a78bfa",
  "features": [
    "Schema-to-Markdown dictionary",
    "Sample distinctness and fill counts",
    "Inferred-description flags"
  ],
  "limitations": [
    "Name-derived descriptions are not verified business definitions.",
    "No data catalog is modified."
  ],
  "fields": [
    {
      "name": "schema",
      "label": "Schema (JSON)",
      "type": "textarea",
      "rows": 7,
      "placeholder": ""
    },
    {
      "name": "sample_csv",
      "label": "Sample CSV (optional)",
      "type": "textarea",
      "rows": 7,
      "placeholder": ""
    }
  ],
  "sample": {
    "schema": "{\"order_id\":\"integer\",\"customer_email\":\"text\",\"total\":\"numeric\",\"created_at\":\"timestamp\"}",
    "sample_csv": "order_id,customer_email,total,created_at\n1,ada@example.com,42.5,2026-01-03\n2,bob@example.com,18.0,2026-01-04"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-data-documentation-agent"
};
