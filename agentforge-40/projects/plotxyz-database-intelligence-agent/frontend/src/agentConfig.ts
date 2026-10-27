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
  "slug": "plotxyz-database-intelligence-agent",
  "title": "Database Intelligence",
  "tagline": "Read the schema like a reviewer, not a parser.",
  "purpose": "Analyzes DDL for primary keys, index coverage, foreign-key-like columns, and workload predicates, then proposes index statements.",
  "accent": "#2dd4bf",
  "features": [
    "DDL structure extraction",
    "Index and primary-key findings",
    "Workload-aware index suggestions"
  ],
  "limitations": [
    "Regex DDL parsing does not cover every dialect.",
    "Suggestions must be benchmarked against real data."
  ],
  "fields": [
    {
      "name": "ddl",
      "label": "CREATE TABLE statements",
      "type": "textarea",
      "rows": 9,
      "placeholder": ""
    },
    {
      "name": "workload",
      "label": "Representative queries",
      "type": "textarea",
      "rows": 5,
      "placeholder": ""
    }
  ],
  "sample": {
    "ddl": "CREATE TABLE users (\n  id INTEGER PRIMARY KEY,\n  email TEXT NOT NULL,\n  created_at TIMESTAMP\n);\nCREATE TABLE orders (\n  id INTEGER,\n  user_id INTEGER,\n  total NUMERIC\n);",
    "workload": "SELECT * FROM orders WHERE user_id = 42 ORDER BY total DESC;"
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-database-intelligence-agent"
};
