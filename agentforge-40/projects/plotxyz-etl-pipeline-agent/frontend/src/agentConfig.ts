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
  "slug": "plotxyz-etl-pipeline-agent",
  "title": "ETL Pipeline",
  "tagline": "Declare the transformation, then execute it safely.",
  "purpose": "Runs a validated, in-memory pipeline of rename, drop, filter, cast, fill, and aggregate steps over CSV data, with a full step log.",
  "accent": "#38bdf8",
  "features": [
    "Allowlisted pipeline operations",
    "Column and operation validation",
    "Step-by-step execution log"
  ],
  "limitations": [
    "No external systems are written.",
    "Only the documented operations are supported."
  ],
  "fields": [
    {
      "name": "csv",
      "label": "Input CSV",
      "type": "textarea",
      "rows": 8,
      "placeholder": ""
    },
    {
      "name": "pipeline",
      "label": "Pipeline steps (JSON)",
      "type": "textarea",
      "rows": 8,
      "placeholder": ""
    }
  ],
  "sample": {
    "csv": "region,amount,status\nnorth,100,paid\nsouth,50,pending\nnorth,75,paid\neast,25,paid",
    "pipeline": "[{\"op\":\"rename\",\"from\":\"amount\",\"to\":\"revenue\"},{\"op\":\"filter\",\"column\":\"status\",\"op_type\":\"eq\",\"value\":\"paid\"},{\"op\":\"aggregate\",\"group_by\":\"region\",\"column\":\"revenue\",\"operation\":\"sum\"}]"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-etl-pipeline-agent"
};
