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
  "slug": "plotxyz-data-lineage-agent",
  "title": "Data Lineage",
  "tagline": "Follow the data from source to dashboard.",
  "purpose": "Validates a declared lineage graph, detects cycles and orphans, and computes upstream and downstream impact for a target node.",
  "accent": "#f59e0b",
  "features": [
    "DAG validation and cycle detection",
    "Upstream/downstream impact",
    "Graph and edge visualization"
  ],
  "limitations": [
    "Only declared lineage is analyzed; runtime lineage is not observed.",
    "The graph is not persisted between requests."
  ],
  "fields": [
    {
      "name": "lineage",
      "label": "Lineage graph (JSON)",
      "type": "textarea",
      "rows": 8,
      "placeholder": ""
    },
    {
      "name": "target",
      "label": "Target node",
      "type": "text",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "lineage": "{\"nodes\":[{\"id\":\"raw_orders\",\"type\":\"source\"},{\"id\":\"clean_orders\",\"type\":\"model\"},{\"id\":\"revenue_dashboard\",\"type\":\"dashboard\"}],\"edges\":[{\"from\":\"raw_orders\",\"to\":\"clean_orders\",\"transform\":\"clean\"},{\"from\":\"clean_orders\",\"to\":\"revenue_dashboard\",\"transform\":\"aggregate\"}]}",
    "target": "revenue_dashboard"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-data-lineage-agent"
};
