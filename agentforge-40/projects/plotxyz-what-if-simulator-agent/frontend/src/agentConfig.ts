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
  "slug": "plotxyz-what-if-simulator-agent",
  "title": "What-If Simulator",
  "tagline": "Make the assumptions visible, then do the math.",
  "purpose": "Projects revenue under multiple explicit growth, churn, and margin scenarios using transparent monthly compounding formulas.",
  "accent": "#a78bfa",
  "features": [
    "Multi-scenario projections",
    "Transparent formulas and assumptions",
    "Scenario comparison chart"
  ],
  "limitations": [
    "Deterministic arithmetic, not a forecast.",
    "Output quality depends entirely on supplied assumptions."
  ],
  "fields": [
    {
      "name": "baseline",
      "label": "Baseline (JSON)",
      "type": "textarea",
      "rows": 6,
      "placeholder": ""
    },
    {
      "name": "scenarios",
      "label": "Scenarios (JSON)",
      "type": "textarea",
      "rows": 7,
      "placeholder": ""
    }
  ],
  "sample": {
    "baseline": "{\"revenue\":100000,\"growth_rate_pct\":4,\"churn_rate_pct\":2,\"gross_margin_pct\":70,\"months\":12}",
    "scenarios": "[{\"name\":\"Base\",\"growth_delta_pct\":0,\"churn_delta_pct\":0},{\"name\":\"Churn spike\",\"growth_delta_pct\":0,\"churn_delta_pct\":3},{\"name\":\"Growth push\",\"growth_delta_pct\":2,\"churn_delta_pct\":-1}]"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-what-if-simulator-agent"
};
