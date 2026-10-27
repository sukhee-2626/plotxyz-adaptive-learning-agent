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
  "slug": "plotxyz-multi-agent-project-manager",
  "title": "Multi-Agent Project Manager",
  "tagline": "Four local handlers, one delivery plan.",
  "purpose": "Delegates tasks to implemented planner, estimator, risk, and reviewer handlers, then combines their outputs into a capacity-checked project plan.",
  "accent": "#34d399",
  "features": [
    "Deterministic planning and estimation handlers",
    "Risk detection and acceptance criteria",
    "Capacity feasibility check"
  ],
  "limitations": [
    "Estimates are heuristics, not commitments.",
    "No external project-management system is modified."
  ],
  "fields": [
    {
      "name": "brief",
      "label": "Project brief",
      "type": "textarea",
      "rows": 5,
      "placeholder": ""
    },
    {
      "name": "tasks",
      "label": "Tasks (one per line)",
      "type": "textarea",
      "rows": 8,
      "placeholder": ""
    },
    {
      "name": "team_size",
      "label": "Team size",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    },
    {
      "name": "deadline_days",
      "label": "Deadline (days)",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "brief": "Launch a customer feedback portal.",
    "tasks": "Research support pain points\nDesign the submission flow\nBuild the API and database\nRun accessibility review\nDeploy to production",
    "team_size": 3,
    "deadline_days": 10
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-multi-agent-project-manager"
};
