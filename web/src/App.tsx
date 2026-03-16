import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";

import { ApiRequestError, api } from "./api";
import { ATTR_CN } from "./copy";
import { EdgeWarnings } from "./components/EdgeWarnings";
import { MarkdownText } from "./components/MarkdownText";
import { RadarChart } from "./components/RadarChart";
import type { ArchiveResponse, PublicScreen } from "./types";

const ATTRS = ["stamina", "skill", "mind", "academics", "social", "finance"] as const;
const ALLOC_TOTAL = 250;
const ALLOC_MIN = 25;
const ALLOC_MAX = 60;

type ResultModal = {
  text: string;
  next: PublicScreen;
};

function getWarningAttrs(screen: PublicScreen | null): string[] {
  if (!screen) return [];
  const fromPayload = screen.payload.warning_attrs;
  if (Array.isArray(fromPayload)) return fromPayload as string[];
  if (Array.isArray(screen.warning_attrs)) return screen.warning_attrs;
  return [];
}

function statusCn(status: string): string {
  const map: Record<string, string> = {
    in_progress: "进行中",
    finished: "已完成",
    collapsed: "崩解中止"
  };
  return map[status] ?? status;
}

function asPublicScreen(value: unknown): PublicScreen | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  if (
    typeof raw.run_id !== "string" ||
    typeof raw.status !== "string" ||
    typeof raw.week !== "number" ||
    typeof raw.screen !== "string" ||
    typeof raw.payload !== "object" ||
    raw.payload === null
  ) {
    return null;
  }
  return {
    run_id: raw.run_id,
    status: raw.status,
    week: raw.week,
    screen: raw.screen as PublicScreen["screen"],
    payload: raw.payload as Record<string, unknown>
  };
}

function allocationWarningText(total: number): string | null {
  if (total === ALLOC_TOTAL) return null;
  if (total > ALLOC_TOTAL) return `总点数超过${ALLOC_TOTAL}（当前 ${total}），请减少 ${total - ALLOC_TOTAL} 点。`;
  return `总点数不足${ALLOC_TOTAL}（当前 ${total}），还需分配 ${ALLOC_TOTAL - total} 点。`;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export default function App() {
  const [screen, setScreen] = useState<PublicScreen | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [resultModal, setResultModal] = useState<ResultModal | null>(null);
  const [showOpening, setShowOpening] = useState(false);
  const [voiceLineIndex, setVoiceLineIndex] = useState(0);

  const [screenHistory, setScreenHistory] = useState<PublicScreen[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1); // -1 means "live/latest"

  const [sessionMode, setSessionMode] = useState<"guest" | "user">("guest");
  const [archive, setArchive] = useState<ArchiveResponse | null>(null);
  const [authUsername, setAuthUsername] = useState("");
  const [authPassword, setAuthPassword] = useState("");

  const [allocation, setAllocation] = useState<Record<string, number>>({
    stamina: 42,
    skill: 42,
    mind: 42,
    academics: 42,
    social: 41,
    finance: 41
  });

  const allocationTotal = useMemo(() => ATTRS.reduce((sum, attr) => sum + allocation[attr], 0), [allocation]);
  const allocationWarning = useMemo(() => allocationWarningText(allocationTotal), [allocationTotal]);
  const isViewingHistory = historyIndex !== -1;

  const refreshArchive = async () => {
    const next = await api.getArchive();
    setArchive(next);
  };

  const applyCurrentScreen = (current: PublicScreen) => {
    setScreen(current);
    setShowOpening(current.screen === "allocation");
    setHistoryIndex(-1);
    setScreenHistory((prev) => {
      if (prev.length > 0 && prev[prev.length - 1].run_id !== current.run_id) {
        return [current];
      }
      const last = prev[prev.length - 1];
      if (last && last.run_id === current.run_id && last.week === current.week && last.screen === current.screen && last.status === current.status) {
        return prev;
      }
      const next = [...prev, current];
      return next.length > 60 ? next.slice(next.length - 60) : next;
    });
  };

  const loadGuestContext = async () => {
    setSessionMode("guest");

    await api.guestInit();
    const active = await api.getActiveRun();

    let current: PublicScreen;
    if ((active as { run?: null }).run === null) {
      const created = await api.createRun();
      current = await api.getRun(created.run_id);
    } else {
      current = active as PublicScreen;
    }

    applyCurrentScreen(current);
    await refreshArchive();
  };

  const loadUserContext = async (preferredRunId?: string) => {
    setSessionMode("user");

    let listing = await api.listRuns();
    let targetRunId = preferredRunId || listing.runs[0]?.run_id;

    if (!targetRunId) {
      const created = await api.createRun();
      targetRunId = created.run_id;
      listing = await api.listRuns();
    }

    const current = await api.getRun(targetRunId);
    applyCurrentScreen(current);
    await refreshArchive();
  };

  useEffect(() => {
    const bootstrap = async () => {
      try {
        setLoading(true);
        setError(null);
        try {
          await loadUserContext();
        } catch (err) {
          if (err instanceof ApiRequestError && (err.status === 400 || err.status === 401 || err.status === 404)) {
            await loadGuestContext();
          } else {
            throw err;
          }
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    };

    void bootstrap();
  }, []);

  useEffect(() => {
    if (!showOpening || !screen || screen.screen !== "allocation") return;
    const intro = screen.payload.intro as Record<string, unknown>;
    const opening = intro?.opening as Record<string, unknown>;
    const lines = (opening?.voiceover_lines_cn ?? []) as string[];
    if (lines.length === 0) return;

    setVoiceLineIndex(0);
    const timer = window.setInterval(() => {
      setVoiceLineIndex((v) => {
        if (v >= lines.length) {
          window.clearInterval(timer);
          return v;
        }
        return v + 1;
      });
    }, 340);

    return () => window.clearInterval(timer);
  }, [showOpening, screen]);

  const warningAttrs = getWarningAttrs(screen);

  const handleBack = () => {
    if (resultModal) {
      setResultModal(null);
      return;
    }
    if (screen?.screen === "allocation" && !showOpening) {
      setShowOpening(true);
      return;
    }
    if (screenHistory.length < 2) return;
    const currentPos = historyIndex === -1 ? screenHistory.length - 1 : historyIndex;
    if (currentPos <= 0) return;

    const targetPos = currentPos - 1;
    const target = screenHistory[targetPos];
    setScreen(target);
    setShowOpening(target.screen === "allocation");
    setHistoryIndex(targetPos);
  };

  const handleReturnToLive = () => {
    if (screenHistory.length === 0) return;
    const live = screenHistory[screenHistory.length - 1];
    setScreen(live);
    setShowOpening(live.screen === "allocation");
    setHistoryIndex(-1);
  };

  const handleRegister = async () => {
    try {
      if (isViewingHistory) {
        setError("当前处于回看模式，请先返回当前进度。");
        return;
      }
      if (!authUsername || !authPassword) {
        setError("请输入用户名和密码。\n用户名最少3位，密码最少6位。");
        return;
      }
      setActionBusy(true);
      setError(null);
      await api.register(authUsername, authPassword);
      await api.login(authUsername, authPassword);
      await loadUserContext();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActionBusy(false);
    }
  };

  const handleLogin = async () => {
    try {
      if (isViewingHistory) {
        setError("当前处于回看模式，请先返回当前进度。");
        return;
      }
      if (!authUsername || !authPassword) {
        setError("请输入用户名和密码。");
        return;
      }
      setActionBusy(true);
      setError(null);
      await api.login(authUsername, authPassword);
      await loadUserContext();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActionBusy(false);
    }
  };

  const handleLogout = async () => {
    try {
      if (isViewingHistory) {
        setError("当前处于回看模式，请先返回当前进度。");
        return;
      }
      setActionBusy(true);
      setError(null);
      await api.logout();
      await loadGuestContext();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActionBusy(false);
    }
  };

  const handleCreateRun = async () => {
    if (!screen) return;
    try {
      if (isViewingHistory) {
        setError("当前处于回看模式，请先返回当前进度。");
        return;
      }
      setActionBusy(true);
      setError(null);
      const created = await api.createRun();
      if (sessionMode === "user") {
        await loadUserContext(created.run_id);
      } else {
        const current = await api.getRun(created.run_id);
        applyCurrentScreen(current);
        await refreshArchive();
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActionBusy(false);
    }
  };

  const handleOpenRun = async (runId: string) => {
    try {
      if (isViewingHistory) {
        setError("当前处于回看模式，请先返回当前进度。");
        return;
      }
      setActionBusy(true);
      setError(null);
      const current = await api.getRun(runId);
      applyCurrentScreen(current);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActionBusy(false);
    }
  };

  const submitAllocation = async () => {
    if (!screen) return;
    if (isViewingHistory) {
      setError("当前处于回看模式，请先返回当前进度。");
      return;
    }
    if (allocationTotal !== ALLOC_TOTAL) {
      setError("总点数必须为250。");
      return;
    }

    try {
      setActionBusy(true);
      setError(null);
      setResultModal(null);
      const next = await api.allocate(screen.run_id, allocation);
      setShowOpening(false);
      applyCurrentScreen(next);
      await refreshArchive();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActionBusy(false);
    }
  };

  const ackPersonalityReveal = async () => {
    if (!screen) return;
    try {
      if (isViewingHistory) {
        setError("当前处于回看模式，请先返回当前进度。");
        return;
      }
      setActionBusy(true);
      setError(null);
      const next = await api.ackPersonality(screen.run_id);
      applyCurrentScreen(next);
      await refreshArchive();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActionBusy(false);
    }
  };

  const chooseOption = async (optionId: string) => {
    if (!screen) return;
    try {
      if (isViewingHistory) {
        setError("当前处于回看模式，请先返回当前进度。");
        return;
      }
      setActionBusy(true);
      setError(null);
      const next = await api.choose(screen.run_id, optionId);
      if (next.result_cn) {
        setResultModal({ text: next.result_cn, next });
      } else {
        applyCurrentScreen(next);
      }
      await refreshArchive();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActionBusy(false);
    }
  };

  const chooseFinal = async (tacticId: string) => {
    if (!screen) return;
    try {
      if (isViewingHistory) {
        setError("当前处于回看模式，请先返回当前进度。");
        return;
      }
      setActionBusy(true);
      setError(null);
      const next = await api.chooseFinal(screen.run_id, tacticId);
      applyCurrentScreen(next);
      await refreshArchive();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActionBusy(false);
    }
  };

  const finishRun = async () => {
    if (!screen) return;
    try {
      if (isViewingHistory) {
        setError("当前处于回看模式，请先返回当前进度。");
        return;
      }
      setActionBusy(true);
      setError(null);
      const next = await api.finish(screen.run_id);
      applyCurrentScreen(next);
      await refreshArchive();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActionBusy(false);
    }
  };

  if (loading) {
    return <div className="min-h-screen bg-parchment p-10 font-body text-ink-900">推演准备中…</div>;
  }

  if (!screen) {
    return <div className="min-h-screen bg-parchment p-10 font-body text-danger">未能加载游戏状态。</div>;
  }

  const intro = (screen.payload.intro as Record<string, unknown>) ?? {};
  const opening = (intro.opening as Record<string, unknown>) ?? {};
  const openingLines = ((opening.voiceover_lines_cn ?? []) as string[]).slice(0, voiceLineIndex);

  return (
    <div className="min-h-screen bg-parchment pb-10 text-ink-900">
      <EdgeWarnings warningAttrs={warningAttrs} />

      <div className="mx-auto max-w-5xl px-4 py-6 md:px-8">
        <header className="mb-6 rounded-2xl border border-ink-700/20 bg-ink-50/80 p-5 shadow-panel backdrop-blur">
          <p className="font-body text-xs uppercase tracking-[0.22em] text-ink-700/80">第一阶段 / v3.3.0</p>
          <h1 className="font-heading text-2xl font-semibold md:text-4xl">剑之初程：淬炼之路</h1>
          <p className="mt-2 font-body text-sm text-ink-700">当前进度：第 {screen.week} 周 · 状态：{statusCn(screen.status)}</p>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              onClick={handleBack}
              disabled={actionBusy || (screenHistory.length < 2 && !(screen.screen === "allocation" && !showOpening) && !resultModal)}
              className="rounded bg-white px-3 py-1 text-xs text-ink-900 ring-1 ring-ink-700/20 disabled:opacity-40"
            >
              返回上一步
            </button>
            {isViewingHistory && (
              <button
                onClick={handleReturnToLive}
                disabled={actionBusy}
                className="rounded bg-ink-900 px-3 py-1 text-xs text-white disabled:opacity-40"
              >
                返回当前进度
              </button>
            )}
            {isViewingHistory && <span className="font-body text-xs text-ink-700">回看模式：不可进行选择与提交。</span>}
          </div>

          <div className="mt-4 rounded-xl border border-ink-700/15 bg-white/75 p-3">
            {sessionMode === "guest" ? (
              <div className="space-y-2">
                <p className="font-body text-xs text-ink-700">游客模式，可直接游玩；登录后可管理多个旅程。</p>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={handleCreateRun}
                    disabled={actionBusy || isViewingHistory}
                    className="rounded bg-bronze px-3 py-1 text-xs text-white disabled:opacity-50"
                  >
                    新建旅程
                  </button>
                  <input
                    value={authUsername}
                    onChange={(e) => setAuthUsername(e.target.value)}
                    placeholder="用户名"
                    className="rounded border border-ink-700/25 px-2 py-1 text-sm"
                  />
                  <input
                    type="password"
                    value={authPassword}
                    onChange={(e) => setAuthPassword(e.target.value)}
                    placeholder="密码"
                    className="rounded border border-ink-700/25 px-2 py-1 text-sm"
                  />
                  <button
                    onClick={handleRegister}
                    disabled={actionBusy}
                    className="rounded bg-ink-900 px-3 py-1 text-xs text-white disabled:opacity-50"
                  >
                    注册
                  </button>
                  <button
                    onClick={handleLogin}
                    disabled={actionBusy}
                    className="rounded bg-bronze px-3 py-1 text-xs text-white disabled:opacity-50"
                  >
                    登录
                  </button>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-body text-xs text-ink-700">已登录用户模式，可保留多个旅程。</p>
                  <button
                    onClick={handleCreateRun}
                    disabled={actionBusy}
                    className="rounded bg-bronze px-3 py-1 text-xs text-white disabled:opacity-50"
                  >
                    新建旅程
                  </button>
                  <button
                    onClick={handleLogout}
                    disabled={actionBusy}
                    className="rounded bg-ink-900 px-3 py-1 text-xs text-white disabled:opacity-50"
                  >
                    退出登录
                  </button>
                </div>
              </div>
            )}
          </div>
        </header>

        {error && <div className="mb-4 rounded-xl border border-danger/40 bg-danger/10 px-4 py-3 font-body text-sm text-danger">{error}</div>}

        {archive && (
          <section className="mb-6 grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-ink-700/20 bg-ink-50/90 p-5 shadow-panel">
              <h2 className="font-heading text-xl">旅程记录</h2>
              <div className="mt-3 max-h-60 space-y-2 overflow-auto pr-1">
                {archive.runs.length === 0 ? (
                  <p className="font-body text-sm text-ink-700">还没有可回看的旅程记录。</p>
                ) : (
                  archive.runs.map((run) => (
                    <button
                      key={run.run_id}
                      onClick={() => handleOpenRun(run.run_id)}
                      disabled={actionBusy || isViewingHistory}
                      className="block w-full rounded-xl border border-ink-700/20 bg-white/80 px-3 py-2 text-left transition hover:border-bronze/40 disabled:opacity-50"
                    >
                      <p className="font-heading text-sm">
                        旅程 {run.run_id.slice(0, 8)} · 第 {run.week} 周 · {statusCn(run.status)}
                      </p>
                      <p className="mt-1 font-body text-xs text-ink-700">
                        最近游玩：{formatDateTime(run.updated_at)}
                        {screen?.run_id === run.run_id ? " · 当前查看中" : ""}
                      </p>
                    </button>
                  ))
                )}
              </div>
            </div>

            <div className="rounded-2xl border border-ink-700/20 bg-ink-50/90 p-5 shadow-panel">
              <h2 className="font-heading text-xl">成就记录</h2>
              <div className="mt-3 max-h-60 space-y-2 overflow-auto pr-1">
                {archive.achievement_records.length === 0 ? (
                  <p className="font-body text-sm text-ink-700">当前还没有已获得的成就记录。</p>
                ) : (
                  archive.achievement_records.map((record) => (
                    <div key={`${record.run_id}-${record.achievement_id}`} className="rounded-xl border border-bronze/25 bg-white/80 px-3 py-2">
                      <p className="font-heading text-sm">{record.name_cn}</p>
                      <p className="mt-1 font-body text-xs text-ink-700">{record.desc_cn}</p>
                      <p className="mt-1 font-body text-[11px] text-ink-700/80">
                        旅程 {record.run_id.slice(0, 8)} · {statusCn(record.status)} · {formatDateTime(record.earned_at)}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>
        )}

        <AnimatePresence mode="wait">
          {screen.screen === "allocation" && (
            <motion.section
              key="allocation"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              className="rounded-2xl border border-ink-700/20 bg-ink-50/90 p-5 shadow-panel md:p-8"
            >
              {showOpening ? (
                <div className="space-y-4">
                  <h2 className="font-heading text-2xl">开场</h2>
                  <MarkdownText text={(opening.scene_cn as string) ?? ""} className="font-body text-[15px]" />
                  <div className="rounded-xl border border-bronze/35 bg-white/65 p-4">
                    {openingLines.map((line, idx) => (
                      <p key={idx} className="min-h-5 font-body text-sm leading-7 text-ink-700">
                        {line || "\u00a0"}
                      </p>
                    ))}
                  </div>
                  <button
                    className="rounded-full bg-ink-900 px-5 py-2 font-body text-sm text-ink-50 transition hover:bg-ink-700"
                    onClick={() => setShowOpening(false)}
                  >
                    {String(opening.cta_cn ?? "进入分配")}
                  </button>
                </div>
              ) : (
                <div>
                  <h2 className="font-heading text-2xl md:text-3xl">属性分配</h2>
                  <p className="mt-1 font-body text-sm text-ink-700">总点数：{allocationTotal} / {ALLOC_TOTAL}</p>
                  {allocationWarning && (
                    <p className="mt-2 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 font-body text-sm text-danger">
                      {allocationWarning}
                    </p>
                  )}

                  <div className="mt-6 space-y-4">
                    {((intro.allocation as Record<string, unknown>)?.attributes as Array<Record<string, string>>).map((attr) => (
                      <div key={attr.id} className="rounded-xl border border-ink-700/15 bg-white/70 p-4">
                        <div className="mb-2 flex items-center justify-between">
                          <p className="font-heading text-lg">{attr.name_cn}</p>
                          <span className="rounded-full bg-ink-900 px-3 py-1 font-body text-sm text-white">{allocation[attr.id]}</span>
                        </div>
                        <input
                          type="range"
                          min={ALLOC_MIN}
                          max={ALLOC_MAX}
                          value={allocation[attr.id]}
                          onChange={(e) =>
                            setAllocation((prev) => ({
                              ...prev,
                              [attr.id]: Number(e.target.value)
                            }))
                          }
                          className="w-full accent-bronze"
                        />
                        <p className="mt-2 font-body text-sm text-ink-700">{attr.desc_cn}</p>
                      </div>
                    ))}
                  </div>

                  <button
                    disabled={actionBusy || isViewingHistory || allocationTotal !== ALLOC_TOTAL}
                    className="mt-6 rounded-full bg-bronze px-6 py-2 font-body text-sm font-semibold text-white transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
                    onClick={submitAllocation}
                  >
                    {actionBusy ? "提交中…" : "定影"}
                  </button>
                </div>
              )}
            </motion.section>
          )}

          {screen.screen === "personality_reveal" && (
            <motion.section
              key="personality-reveal"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="rounded-2xl border border-ink-700/20 bg-ink-50/90 p-5 shadow-panel md:p-8"
            >
              <h2 className="font-heading text-2xl">{String(screen.payload.title_cn ?? "人格觉醒：你的初貌")}</h2>
              <p className="mt-4 whitespace-pre-line font-body text-sm leading-7 text-ink-700">
                {String(screen.payload.reveal_cn ?? "")}
              </p>
              <button
                onClick={ackPersonalityReveal}
                disabled={actionBusy || isViewingHistory}
                className="mt-6 rounded-full bg-bronze px-6 py-2 font-body text-sm font-semibold text-white transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {actionBusy ? "处理中…" : String(screen.payload.cta_cn ?? "继续")}
              </button>
            </motion.section>
          )}

          {screen.screen === "week" && (
            <motion.section
              key={`week-${screen.week}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="rounded-2xl border border-ink-700/20 bg-ink-50/90 p-5 shadow-panel md:p-8"
            >
              <h2 className="font-heading text-2xl">{String(screen.payload.title_cn ?? "")}</h2>
              <MarkdownText text={String(screen.payload.narrative_cn ?? "")} className="mt-4 font-body text-[15px]" />
              <div className="mt-6 grid gap-3">
                {((screen.payload.options ?? []) as Array<Record<string, string>>).map((opt) => (
                  <button
                    key={opt.id}
                    className="rounded-xl border border-ink-700/20 bg-white/70 p-4 text-left transition hover:border-bronze/60 hover:bg-white"
                    onClick={() => chooseOption(opt.id)}
                    disabled={actionBusy || isViewingHistory}
                  >
                    <p className="font-heading text-lg">{opt.title_cn}</p>
                    <p className="mt-1 font-body text-sm text-ink-700">{opt.desc_cn}</p>
                  </button>
                ))}
              </div>
            </motion.section>
          )}

          {screen.screen === "finals" && (
            <motion.section
              key="finals"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="rounded-2xl border border-ink-700/20 bg-ink-50/90 p-5 shadow-panel md:p-8"
            >
              <h2 className="font-heading text-2xl">{String(screen.payload.title_cn ?? "最终淬炼：决胜一分")}</h2>
              <MarkdownText text={String(screen.payload.narrative_cn ?? "")} className="mt-4 font-body text-[15px]" />

              <div className="mt-6 grid gap-3 md:grid-cols-2">
                {((screen.payload.tactics ?? []) as Array<Record<string, unknown>>).map((tactic) => (
                  <div key={String(tactic.id)} className="rounded-xl border border-ink-700/20 bg-white/70 p-4">
                    <p className="font-heading text-lg">{String(tactic.name_cn)}</p>
                    <p className="mt-1 font-body text-sm text-ink-700">{String(tactic.desc_cn)}</p>
                    <button
                      onClick={() => chooseFinal(String(tactic.id))}
                      disabled={actionBusy || isViewingHistory}
                      className="mt-3 rounded-full bg-ink-900 px-4 py-1.5 font-body text-xs text-white transition enabled:hover:bg-ink-700 disabled:opacity-50"
                    >
                      选择此战术
                    </button>
                  </div>
                ))}
              </div>
            </motion.section>
          )}

          {screen.screen === "final_outcome" && (
            <motion.section
              key="final-outcome"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="rounded-2xl border border-ink-700/20 bg-ink-50/90 p-5 shadow-panel md:p-8"
            >
              {(() => {
                const result = (screen.payload.result as Record<string, unknown>) ?? {};
                return (
                  <>
                    <h2 className="font-heading text-2xl">决赛结果：{String(result.final_result ?? "")}</h2>
                    <p className="mt-2 font-body text-sm text-ink-700">战术：{String(result.tactic_name_cn ?? "")}</p>
                    <p className="font-body text-sm text-ink-700">达标：{String(result.requirements_met ? "是" : "否")}</p>
                    {result.final_tier_cn && <p className="font-body text-sm text-ink-700">胜利档位：{String(result.final_tier_cn)}</p>}
                  </>
                );
              })()}

              <button
                onClick={() => {
                  const next = asPublicScreen(screen.report_payload);
                  if (next) {
                    applyCurrentScreen(next);
                    return;
                  }
                  void finishRun();
                }}
                disabled={actionBusy || isViewingHistory}
                className="mt-5 rounded-full bg-bronze px-5 py-2 font-body text-sm text-white transition enabled:hover:brightness-110 disabled:opacity-50"
              >
                生成年度成长报告
              </button>
            </motion.section>
          )}

          {screen.screen === "collapse" && (
            <motion.section
              key="collapse"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="rounded-2xl border border-danger/30 bg-ink-50/90 p-5 shadow-panel md:p-8"
            >
              {(() => {
                const ending = (screen.payload.ending as Record<string, string>) ?? {};
                const personalityStart = (screen.payload.personality_start_meta as Record<string, string> | undefined) ?? {};
                const personalityEnd = (screen.payload.personality_end_meta as Record<string, string> | undefined) ?? {};
                return (
                  <>
                    <h2 className="font-heading text-2xl text-danger">推演中止：{ending.name_cn}</h2>
                    {personalityStart.name_cn && <p className="mt-3 font-body text-sm text-ink-700">初型人格：{personalityStart.name_cn}</p>}
                    {personalityEnd.name_cn && <p className="font-body text-sm text-ink-700">崩解时人格：{personalityEnd.name_cn}</p>}
                    <p className="mt-4 whitespace-pre-line font-body text-sm leading-7 text-ink-700">{ending.copy_cn}</p>
                  </>
                );
              })()}

              <button
                onClick={finishRun}
                disabled={actionBusy || isViewingHistory}
                className="mt-5 rounded-full bg-ink-900 px-5 py-2 font-body text-sm text-white transition enabled:hover:bg-ink-700 disabled:opacity-50"
              >
                生成报告归档
              </button>
            </motion.section>
          )}

          {screen.screen === "report" && (
            <motion.section
              key="report"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="space-y-5 rounded-2xl border border-ink-700/20 bg-ink-50/90 p-5 shadow-panel md:p-8"
            >
              <h2 className="font-heading text-2xl">第一学年成长报告</h2>
              <div className="grid gap-5 md:grid-cols-2">
                <div className="rounded-xl border border-ink-700/15 bg-white/70 p-4">
                  <RadarChart values={(screen.payload.attributes_end as Record<string, number>) ?? {}} />
                </div>
                <div className="rounded-xl border border-ink-700/15 bg-white/70 p-4">
                  {(() => {
                    const personalityStart = (screen.payload.personality_start_meta as Record<string, string> | undefined) ?? {};
                    const personalityEnd = (screen.payload.personality_end_meta as Record<string, string> | undefined) ?? {};
                    return (
                      <>
                        {personalityStart.name_cn && <p className="font-body text-sm">初型人格：{personalityStart.name_cn}</p>}
                        {personalityEnd.name_cn && <p className="font-body text-sm">终局人格：{personalityEnd.name_cn}</p>}
                      </>
                    );
                  })()}
                  <p className="font-body text-sm">成长积分：{Number(screen.payload.score ?? 0)}</p>
                  <p className="font-body text-sm">评级：{String((screen.payload.grade as Record<string, string>)?.label ?? "")}</p>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    {ATTRS.map((attr) => (
                      <div key={attr} className="rounded bg-ink-100/70 px-2 py-1 font-body text-sm">
                        {ATTR_CN[attr]}：{Number((screen.payload.attributes_end as Record<string, number>)?.[attr] ?? 0)}
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {(() => {
                const sections = (screen.payload.report_sections as Record<string, unknown>) ?? {};
                return (
                  <div className="space-y-3">
                    <MarkdownText text={String(sections.trajectory_summary_cn ?? "")} className="rounded-xl border border-ink-700/15 bg-white/70 p-4 font-body text-sm" />
                    <MarkdownText text={String(sections.coach_note_cn ?? "")} className="rounded-xl border border-ink-700/15 bg-white/70 p-4 font-body text-sm" />
                    <MarkdownText text={String(sections.teammate_note_cn ?? "")} className="rounded-xl border border-ink-700/15 bg-white/70 p-4 font-body text-sm" />
                    {Boolean(sections.final_moment_cn) && (
                      <MarkdownText text={String(sections.final_moment_cn)} className="rounded-xl border border-ink-700/15 bg-white/70 p-4 font-body text-sm" />
                    )}
                  </div>
                );
              })()}

              <div className="rounded-xl border border-ink-700/15 bg-white/70 p-4">
                <h3 className="font-heading text-lg">成就</h3>
                <div className="mt-2 space-y-2">
                  {((screen.payload.achievements ?? []) as Array<Record<string, string>>).map((ach) => (
                    <div key={ach.id} className="rounded border border-bronze/30 bg-bronze/10 px-3 py-2">
                      <p className="font-heading text-sm">{ach.name_cn}</p>
                      <p className="font-body text-xs text-ink-700">{ach.desc_cn}</p>
                    </div>
                  ))}
                </div>
              </div>
            </motion.section>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {resultModal && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/45 p-4"
          >
            <motion.div
              initial={{ y: 10, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: -10, opacity: 0 }}
              className="w-full max-w-xl rounded-2xl bg-ink-50 p-5 shadow-panel"
            >
              <h3 className="font-heading text-xl">本周结果</h3>
              <p className="mt-2 whitespace-pre-line font-body text-sm leading-7 text-ink-700">{resultModal.text}</p>
              <button
                className="mt-4 rounded-full bg-ink-900 px-4 py-2 font-body text-sm text-white"
                onClick={() => {
                  applyCurrentScreen(resultModal.next);
                  setResultModal(null);
                }}
              >
                继续
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
