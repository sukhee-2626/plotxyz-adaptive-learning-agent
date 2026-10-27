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
  "slug": "plotxyz-local-model-benchmark-agent",
  "title": "Local Model Benchmark",
  "tagline": "Measure the machine, not the marketing.",
  "purpose": "Runs a repeatable local JSON serialization workload and reports real latency percentiles and throughput, with an optional health check of a configured Ollama endpoint.",
  "accent": "#a78bfa",
  "features": [
    "Real measured latency percentiles",
    "Repeatable reference workload",
    "Optional local endpoint health check"
  ],
  "limitations": [
    "The reference workload is not model inference and does not report token throughput.",
    "Only environment-configured endpoints are contacted; arbitrary URLs are rejected by design."
  ],
  "fields": [
    {
      "name": "iterations",
      "label": "Iterations",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    },
    {
      "name": "payload_tokens",
      "label": "Payload tokens",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    }
  ],
  "sample": {
    "iterations": 120,
    "payload_tokens": 256
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-local-model-benchmark-agent"
};
