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
  "slug": "plotxyz-adaptive-learning-agent",
  "title": "Adaptive Learning",
  "tagline": "Practice that adjusts to the last answer.",
  "purpose": "Generates cloze questions from supplied study material, grades submitted answers, and moves the next session up or down in difficulty.",
  "accent": "#facc15",
  "features": [
    "Cloze question generation",
    "Answer grading and feedback",
    "Difficulty adaptation"
  ],
  "limitations": [
    "Generated questions are only as good as the supplied text.",
    "The agent does not understand arbitrary free-text answers."
  ],
  "fields": [
    {
      "name": "study_text",
      "label": "Study material",
      "type": "textarea",
      "rows": 9,
      "placeholder": ""
    },
    {
      "name": "difficulty",
      "label": "Difficulty (1-3)",
      "type": "number",
      "rows": 4,
      "placeholder": ""
    },
    {
      "name": "answers",
      "label": "Answers (JSON, optional)",
      "type": "textarea",
      "rows": 5,
      "placeholder": ""
    }
  ],
  "sample": {
    "study_text": "Photosynthesis converts light energy into chemical energy. Plants use chlorophyll to absorb light in the chloroplast. Carbon dioxide and water are converted into glucose and oxygen. The process supports most food chains on Earth.",
    "difficulty": 2,
    "answers": ""
  },
  "repo": "https://github.com/sukhee-2626/plotxyz-adaptive-learning-agent"
};
