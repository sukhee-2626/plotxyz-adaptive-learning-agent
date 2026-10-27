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
  "slug": "plotxyz-sql-performance-agent",
  "title": "SQL Performance",
  "tagline": "Read the plan, find the expensive part.",
  "purpose": "Parses EXPLAIN output for scans, joins, sorts, costs, and row estimates, then explains likely bottlenecks and suggests indexes or statistics work.",
  "accent": "#60a5fa",
  "features": [
    "Plan-node extraction",
    "Cost and row-estimate signals",
    "Index and statistics recommendations"
  ],
  "limitations": [
    "No database connection is made.",
    "Recommendations must be validated with real plans and data."
  ],
  "fields": [
    {
      "name": "explain",
      "label": "EXPLAIN output",
      "type": "textarea",
      "rows": 9,
      "placeholder": ""
    },
    {
      "name": "query",
      "label": "Query (optional)",
      "type": "textarea",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "explain": "Limit  (cost=100.00..120.00 rows=10 width=64)\n  ->  Sort  (cost=100.00..110.00 rows=1000 width=64)\n        ->  Seq Scan on orders  (cost=0.00..80.00 rows=50000 width=64)\n              Filter: (status = 'paid'::text)",
    "query": "SELECT * FROM orders WHERE status = 'paid' ORDER BY total DESC LIMIT 10;"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-sql-performance-agent"
};
