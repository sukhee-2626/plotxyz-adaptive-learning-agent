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
  "slug": "plotxyz-workflow-builder-agent",
  "title": "Workflow Builder",
  "tagline": "Compose safe transformations, not shell scripts.",
  "purpose": "Executes a validated workflow of allowlisted in-memory operations (set, case conversion, replace, extract, append, multiply, filter) over JSON data.",
  "accent": "#38bdf8",
  "features": [
    "Allowlisted operation set",
    "Path-level validation and step log",
    "In-memory JSON transformation"
  ],
  "limitations": [
    "No shell, HTTP, or filesystem operations are available.",
    "The workflow is limited to 50 steps and the documented operations."
  ],
  "fields": [
    {
      "name": "data",
      "label": "Input JSON",
      "type": "textarea",
      "rows": 7,
      "placeholder": ""
    },
    {
      "name": "workflow",
      "label": "Workflow steps (JSON)",
      "type": "textarea",
      "rows": 8,
      "placeholder": ""
    }
  ],
  "sample": {
    "data": "{\"user\":{\"name\":\"ada\"},\"items\":[{\"name\":\"a\",\"score\":5},{\"name\":\"b\",\"score\":15},{\"name\":\"c\",\"score\":25}]}",
    "workflow": "[{\"op\":\"uppercase\",\"path\":\"user.name\"},{\"op\":\"filter\",\"path\":\"items\",\"field\":\"score\",\"op_type\":\"gt\",\"value\":10},{\"op\":\"extract\",\"path\":\"items\",\"as\":\"filtered\"}]"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-workflow-builder-agent"
};
