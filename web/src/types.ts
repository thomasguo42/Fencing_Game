export type ScreenType =
  | "start"
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
  result_segments?: string[];
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
  score?: number | null;
  grade_label?: string | null;
  final_result?: string | null;
};

export type RunsListResponse = {
  runs: RunListItem[];
};

export type AchievementRecord = {
  achievement_id: string;
  name_cn: string;
  desc_cn: string;
  run_id: string;
  status: string;
  week: number;
  earned_at: string;
};

export type HistoryRecord = {
  run_id: string;
  status: string;
  week: number;
  played_at: string;
  score?: number | null;
  grade_label?: string | null;
  final_result?: string | null;
  attributes_end?: Record<string, number> | null;
  personality_end_meta?: {
    id?: string | null;
    name_cn?: string | null;
    copy_cn?: { short?: string; long?: string } | null;
  } | null;
  collapse_ending_name_cn?: string | null;
};

export type AchievementCatalogItem = {
  achievement_id: string;
  name_cn: string;
  desc_cn: string;
  unlocked: boolean;
};

export type PlayQuota = {
  remaining_today: number;
  base_limit: number;
  base_used: number;
  bonus_limit: number;
  bonus_earned: number;
  total_limit: number;
  can_start_game: boolean;
};

export type ArchiveResponse = {
  runs: RunListItem[];
  history_records: HistoryRecord[];
  achievement_records: AchievementRecord[];
  achievement_catalog: AchievementCatalogItem[];
  play_quota: PlayQuota;
};

export type UserProfile = {
  username: string;
  display_name?: string | null;
  phone_number?: string | null;
  external_user_id?: string | null;
};

export type ShareInvite = {
  invite_token: string;
  share_url: string;
  page_path: string;
  qr_data_url: string;
  bonus_limit: number;
};

export type ShareRedeem = {
  ok: boolean;
  granted_bonus: boolean;
  message: string;
  play_quota: PlayQuota;
};

export type LeaderboardEntry = {
  rank: number;
  display_name_masked: string;
  score: number;
  run_id?: string | null;
  achieved_at?: string | null;
};

export type LeaderboardResponse = {
  board: string;
  page: number;
  page_size: number;
  total_entries: number;
  period_start?: string | null;
  period_end?: string | null;
  entries: LeaderboardEntry[];
  self_entry?: LeaderboardEntry | null;
};
