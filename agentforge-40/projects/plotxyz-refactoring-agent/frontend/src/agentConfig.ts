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
  "slug": "plotxyz-refactoring-agent",
  "title": "Refactoring",
  "tagline": "Small, reviewable improvements beat risky rewrites.",
  "purpose": "Finds long functions, None equality, explicit empty checks, and magic numbers, then proposes syntax-validated before/after patches.",
  "accent": "#c084fc",
  "features": [
    "Targeted refactoring opportunities",
    "Validated before/after patches",
    "Readability-focused scoring"
  ],
  "limitations": [
    "Patches are syntactic and must be covered by tests.",
    "Large architectural rewrites are out of scope."
  ],
  "fields": [
    {
      "name": "code",
      "label": "Python source",
      "type": "textarea",
      "rows": 10,
      "placeholder": ""
    },
    {
      "name": "focus",
      "label": "Focus (readability or complexity)",
      "type": "text",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "code": "def process(records):\n    total = 0\n    for record in records:\n        if record[\"status\"] == None:\n            continue\n        total += record[\"amount\"] * 3600\n    return total",
    "focus": "readability"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-refactoring-agent"
};
