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
  "slug": "plotxyz-computer-health-agent",
  "title": "Computer Health",
  "tagline": "Read the symptoms, not just the percentages.",
  "purpose": "Analyzes a supplied system report and flags CPU, memory, disk, temperature, and failed-service thresholds with a health score.",
  "accent": "#fb923c",
  "features": [
    "Threshold-based health checks",
    "Severity-ranked findings",
    "Clear metric table"
  ],
  "limitations": [
    "Uses only the supplied metrics; no system access is performed.",
    "Thresholds are generic and may need tuning per device."
  ],
  "fields": [
    {
      "name": "metrics",
      "label": "System metrics (JSON)",
      "type": "textarea",
      "rows": 7,
      "placeholder": ""
    }
  ],
  "sample": {
    "metrics": "{\"cpu_percent\": 92, \"memory_percent\": 71, \"disk_percent\": 55, \"temperature_c\": 84, \"failed_services\": 1}"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-computer-health-agent"
};
