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
  "slug": "plotxyz-startup-cofounder-agent",
  "title": "Startup Co-founder",
  "tagline": "From idea to a scoped MVP and a realistic roadmap.",
  "purpose": "Turns an idea, audience, constraints, and timeline into an MVP specification, personas, phased roadmap, prioritized backlog, and risks.",
  "accent": "#f59e0b",
  "features": [
    "MVP scope and personas",
    "Phased roadmap and backlog",
    "Risk flags and explicit assumptions"
  ],
  "limitations": [
    "Output is a rule-based first draft, not market validation.",
    "Estimates are rough and should be challenged by the delivery team."
  ],
  "fields": [
    {
      "name": "idea",
      "label": "Product idea",
      "type": "textarea",
      "rows": 6,
      "placeholder": ""
    },
    {
      "name": "audience",
      "label": "Target audience",
      "type": "text",
      "rows": 4,
      "placeholder": ""
    },
    {
      "name": "constraints",
      "label": "Constraints",
      "type": "textarea",
      "rows": 4,
      "placeholder": ""
    },
    {
      "name": "timeline_weeks",
      "label": "Timeline (weeks)",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "idea": "An AI copilot for independent coffee shops that forecasts demand and reduces waste.",
    "audience": "Independent coffee shop owners",
    "constraints": "Two founders, $20k budget, 8 weeks",
    "timeline_weeks": 8
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-startup-cofounder-agent"
};
