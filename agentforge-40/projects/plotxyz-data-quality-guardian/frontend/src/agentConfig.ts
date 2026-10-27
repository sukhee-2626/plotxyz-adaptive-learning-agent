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
  "slug": "plotxyz-data-quality-guardian",
  "title": "Data Quality Guardian",
  "tagline": "Catch bad rows before they reach the warehouse.",
  "purpose": "Profiles CSV data for missing values, duplicate rows, inferred types, invalid values, and an overall quality score.",
  "accent": "#4ade80",
  "features": [
    "Missingness and duplicate detection",
    "Type inference and invalid-value counts",
    "Quality score and findings"
  ],
  "limitations": [
    "Type inference uses a sample of values.",
    "The agent does not repair or write data."
  ],
  "fields": [
    {
      "name": "csv",
      "label": "CSV data",
      "type": "textarea",
      "rows": 10,
      "placeholder": ""
    }
  ],
  "sample": {
    "csv": "email,age,plan\nada@example.com,36,pro\nada@example.com,36,pro\n,41,basic\nbob@example,abc,pro\ncara@example.com,29,"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-data-quality-guardian"
};
