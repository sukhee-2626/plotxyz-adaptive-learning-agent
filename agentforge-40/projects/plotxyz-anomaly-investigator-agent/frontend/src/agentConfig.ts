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
  "slug": "plotxyz-anomaly-investigator-agent",
  "title": "Anomaly Investigator",
  "tagline": "Find the odd points and rank the likely patterns.",
  "purpose": "Flags anomalies in a numeric CSV column using z-scores and IQR, then ranks candidate explanations such as isolated spikes, clusters, or distribution shifts.",
  "accent": "#fb7185",
  "features": [
    "Z-score and IQR anomaly detection",
    "Candidate pattern ranking",
    "Value chart and anomaly table"
  ],
  "limitations": [
    "Flags are statistical candidates, not causal explanations.",
    "The agent does not inspect upstream systems."
  ],
  "fields": [
    {
      "name": "csv",
      "label": "CSV data",
      "type": "textarea",
      "rows": 9,
      "placeholder": ""
    },
    {
      "name": "column",
      "label": "Numeric column (optional)",
      "type": "text",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "csv": "day,value\n1,100\n2,102\n3,98\n4,101\n5,99\n6,100\n7,103\n8,1000\n9,97\n10,102",
    "column": "value"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-anomaly-investigator-agent"
};
