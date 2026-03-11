export type ScreenType =
  | "allocation"
  | "week"
  | "personality_reveal"
  | "finals"
  | "final_outcome"
  | "collapse"
  | "report";

export type PublicScreen = {
  run_id: string;
  status: string;
  week: number;
  screen: ScreenType;
  payload: Record<string, unknown>;
  result_cn?: string;
  report_payload?: PublicScreen;
  personality_reveal?: {
    title_cn?: string;
    cta_cn?: string;
    reveal_cn?: string;
    personality?: { id?: string; name_cn?: string; copy_cn?: { short?: string; long?: string } };
  };
  warning_attrs?: string[];
  chosen_option_id?: string;
};

export type ApiError = {
  detail?: string;
};

export type RunListItem = {
  run_id: string;
  status: string;
  week: number;
  created_at: string;
  updated_at: string;
};

export type RunsListResponse = {
  runs: RunListItem[];
};
