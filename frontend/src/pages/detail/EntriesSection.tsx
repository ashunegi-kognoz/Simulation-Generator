import { useEffect, useState } from "react";
import { ApiError, api } from "../../api/client";
import type {
  Posture,
  PostureScheme,
  SimContent,
  SimContentDecision,
  TypeSet,
} from "../../api/types";
import { Banner, Panel, Spinner } from "../../components/ui";
import { cn } from "../../lib/cn";

const POSTURE_STYLE: Record<Posture, string> = {
  Protect: "bg-petrol-soft text-petrol",
  Enable: "bg-grass-soft text-grass",
  Hybrid: "bg-amber-soft text-amber",
  Defer: "bg-canvas text-muted",
};

type Path = (string | number)[];
type SetFn = (path: Path, value: string) => void;

function setIn(obj: unknown, path: Path, value: string): unknown {
  if (path.length === 0) return value;
  const [head, ...rest] = path;
  const src = obj as Record<string | number, unknown>;
  const clone: Record<string | number, unknown> = Array.isArray(obj)
    ? (obj.slice() as unknown as Record<string | number, unknown>)
    : { ...(src ?? {}) };
  clone[head] = setIn(src?.[head], rest, value);
  return clone;
}

const STANCE_STYLES = [
  "bg-petrol-soft text-petrol",
  "bg-grass-soft text-grass",
  "bg-amber-soft text-amber",
  "bg-canvas text-muted",
];

function resolveStance(
  posture: string,
  scheme?: PostureScheme,
  typeSet?: TypeSet,
): { label: string; cls: string } {
  if (typeSet) {
    const idx = typeSet.stances.findIndex((st) => st.key === posture);
    if (idx >= 0) {
      return { label: typeSet.stances[idx].label, cls: STANCE_STYLES[idx % STANCE_STYLES.length] };
    }
  }
  const cls = POSTURE_STYLE[posture as Posture] ?? "bg-canvas text-muted";
  if (scheme) {
    const map: Record<string, string> = {
      Protect: scheme.protect_label,
      Enable: scheme.enable_label,
      Hybrid: scheme.hybrid_label,
      Defer: scheme.defer_label,
    };
    return { label: map[posture] || posture, cls };
  }
  return { label: posture, cls };
}

function PostureTag({ posture, scheme, typeSet }: { posture: string; scheme?: PostureScheme; typeSet?: TypeSet }) {
  const { label, cls } = resolveStance(posture, scheme, typeSet);
  return (
    <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-semibold", cls)}>
      {label}
    </span>
  );
}

function EditableText({
  editing,
  value,
  onChange,
  long,
}: {
  editing: boolean;
  value: string;
  onChange: (v: string) => void;
  long?: boolean;
}) {
  if (!editing) {
    return <p className="whitespace-pre-wrap text-sm leading-relaxed text-ink">{value || "—"}</p>;
  }
  return long ? (
    <textarea
      className="input min-h-[90px] w-full text-sm"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ) : (
    <input className="input w-full text-sm" value={value} onChange={(e) => onChange(e.target.value)} />
  );
}

function Field({
  label,
  value,
  editing,
  onChange,
  long = true,
}: {
  label: string;
  value: string;
  editing: boolean;
  onChange: (v: string) => void;
  long?: boolean;
}) {
  return (
    <div>
      <div className="eyebrow mb-1">{label}</div>
      <EditableText editing={editing} value={value} onChange={onChange} long={long} />
    </div>
  );
}

function DecisionBoard({
  decisions,
  scheme,
  typeSet,
  editing,
  set,
  basePath,
}: {
  decisions: SimContentDecision[];
  scheme?: PostureScheme;
  typeSet?: TypeSet;
  editing: boolean;
  set: SetFn;
  basePath: Path;
}) {
  return (
    <div className="space-y-3">
      {decisions.map((d, di) => (
        <div key={di} className="rounded-xl border border-line bg-canvas p-3">
          <div className="flex items-center justify-between gap-2">
            <div className="flex-1 text-sm font-medium text-ink">
              <span className="num text-muted">D{d.decision_number}</span>{" "}
              {editing ? (
                <input
                  className="input mt-1 w-full text-sm"
                  value={d.title}
                  onChange={(e) => set([...basePath, di, "title"], e.target.value)}
                />
              ) : (
                <>· {d.title}</>
              )}
            </div>
            <span className="rounded-full bg-panel px-2 py-0.5 text-[11px] font-medium text-ink">
              {d.dimension}
            </span>
          </div>
          {editing ? (
            <textarea
              className="input mt-2 min-h-[56px] w-full text-sm"
              value={d.question}
              onChange={(e) => set([...basePath, di, "question"], e.target.value)}
            />
          ) : (
            <p className="mt-1 text-sm text-muted">{d.question}</p>
          )}
          <div className="mt-3 space-y-2">
            {d.options.map((o, oi) => (
              <div key={oi} className="rounded-lg border border-line bg-panel px-3 py-2">
                <div className="mb-0.5 flex items-center gap-2">
                  {editing ? (
                    <input
                      className="input w-full text-xs font-semibold"
                      value={o.label}
                      onChange={(e) => set([...basePath, di, "options", oi, "label"], e.target.value)}
                    />
                  ) : (
                    <span className="num text-xs font-semibold text-ink">{o.label}</span>
                  )}
                  <PostureTag posture={o.posture} scheme={scheme} typeSet={typeSet} />
                </div>
                {editing ? (
                  <textarea
                    className="input min-h-[70px] w-full text-sm"
                    value={o.content}
                    onChange={(e) => set([...basePath, di, "options", oi, "content"], e.target.value)}
                  />
                ) : (
                  <p className="text-sm text-ink">{o.content}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function RoundBlock({
  roundKey,
  round,
  scheme,
  typeSet,
  editing,
  set,
}: {
  roundKey: string;
  round: SimContent["rounds"][string];
  scheme?: PostureScheme;
  typeSet?: TypeSet;
  editing: boolean;
  set: SetFn;
}) {
  const num = roundKey.replace("round_", "");
  return (
    <Panel
      eyebrow={`Round ${num}`}
      title={round.round_type === "group" ? "Group round" : "Individual round"}
    >
      {round.participants && (
        <div className="space-y-4">
          {Object.entries(round.participants).map(([pid, p]) => {
            const pPath: Path = ["rounds", roundKey, "participants", pid];
            return (
              <div key={pid} className="rounded-xl border border-line p-4">
                <div className="mb-3 flex items-center gap-2">
                  <span className="num rounded-md bg-ink px-2 py-0.5 text-xs font-semibold text-white">
                    {pid}
                  </span>
                  <span className="text-sm font-medium text-ink">Participant view</span>
                </div>
                <div className="space-y-3">
                  <Field
                    label="Role"
                    value={p.role_data}
                    editing={editing}
                    onChange={(v) => set([...pPath, "role_data"], v)}
                  />
                  <Field
                    label="Your situation"
                    value={p.situation_data}
                    editing={editing}
                    onChange={(v) => set([...pPath, "situation_data"], v)}
                  />
                  <div>
                    <div className="eyebrow mb-1.5">Decision board</div>
                    <DecisionBoard
                      decisions={p.decision_board}
                      scheme={scheme} typeSet={typeSet}
                      editing={editing}
                      set={set}
                      basePath={[...pPath, "decision_board"]}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {round.teams && (
        <div className="space-y-4">
          {Object.entries(round.teams).map(([tid, t]) => {
            const tPath: Path = ["rounds", roundKey, "teams", tid];
            return (
              <div key={tid} className="rounded-xl border border-line p-4">
                <div className="mb-3 flex flex-wrap items-center gap-2">
                  <span className="rounded-md bg-ink px-2 py-0.5 text-xs font-semibold text-white">
                    {t.team_name}
                  </span>
                  <span className="num text-xs text-muted">{t.participant_ids.join(", ")}</span>
                </div>
                <Field
                  label="Scenario"
                  value={t.scenario_data}
                  editing={editing}
                  onChange={(v) => set([...tPath, "scenario_data"], v)}
                />
                {t.situation_data ? (
                  <div className="mt-3">
                    <Field
                      label="Team situation (shared by all members)"
                      value={t.situation_data}
                      editing={editing}
                      onChange={(v) => set([...tPath, "situation_data"], v)}
                    />
                  </div>
                ) : null}
                <div className="mt-4 space-y-4">
                  {Object.entries(t.members).map(([pid, m]) => {
                    const mPath: Path = [...tPath, "members", pid];
                    return (
                      <div key={pid} className="rounded-xl border border-line bg-canvas p-3">
                        <div className="mb-2 flex items-center gap-2">
                          <span className="num rounded-md bg-panel px-2 py-0.5 text-xs font-semibold text-ink">
                            {pid}
                          </span>
                          <span className="text-xs text-muted">member view</span>
                        </div>
                        {!t.situation_data && (
                          <Field
                            label="Your situation"
                            value={m.situation_data}
                            editing={editing}
                            onChange={(v) => set([...mPath, "situation_data"], v)}
                          />
                        )}
                        <div className="mt-3">
                          <div className="eyebrow mb-1.5">Decision board</div>
                          <DecisionBoard
                            decisions={m.decision_board}
                            scheme={scheme} typeSet={typeSet}
                            editing={editing}
                            set={set}
                            basePath={[...mPath, "decision_board"]}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

export function EntriesSection({
  simulationId,
  token,
}: {
  simulationId: string;
  token: string;
}) {
  const [content, setContent] = useState<SimContent | null>(null);
  const [edited, setEdited] = useState<SimContent | null>(null);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    setEditing(false);
    setEdited(null);
    api
      .getContent(simulationId, token)
      .then((res) => {
        if (alive) setContent(res.sim_data);
      })
      .catch((e) => {
        if (alive) setError(e instanceof ApiError ? e.message : "Couldn't load content.");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [simulationId, token]);

  const set: SetFn = (path, value) =>
    setEdited((prev) => (prev ? (setIn(prev, path, value) as SimContent) : prev));

  function startEdit() {
    setEdited(structuredClone(content));
    setEditing(true);
    setSaveErr(null);
  }
  function cancel() {
    setEditing(false);
    setEdited(null);
    setSaveErr(null);
  }
  async function save() {
    if (!edited) return;
    setSaving(true);
    setSaveErr(null);
    try {
      await api.updateContent(simulationId, token, edited);
      setContent(edited);
      setEditing(false);
      setEdited(null);
    } catch (e) {
      setSaveErr(e instanceof ApiError ? e.message : "Couldn't save changes.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <Panel eyebrow="Simulation entries" title="Generated content">
        <Spinner label="Loading generated content…" />
      </Panel>
    );
  }
  if (error) {
    return (
      <Panel eyebrow="Simulation entries" title="Generated content">
        <Banner tone="error" title="Couldn't load content">{error}</Banner>
      </Panel>
    );
  }
  if (!content) {
    return (
      <Panel eyebrow="Simulation entries" title="Generated content">
        <Banner tone="empty">
          No generated content yet. Once the simulation finishes generating, every participant and
          team's content appears here.
        </Banner>
      </Panel>
    );
  }

  const view = editing && edited ? edited : content;
  const c = view.common_data;
  const ps = c.posture_scheme;

  return (
    <div className="space-y-6">
      <div className="panel flex flex-wrap items-center justify-between gap-3 px-4 py-3">
        <div>
          <div className="font-medium text-ink">Generated content</div>
          <p className="text-xs text-muted">
            {editing
              ? "Editing — changes are saved to the database and reach live participant sessions."
              : "Review the full generated content. You can edit it and save back to the database."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {editing ? (
            <>
              <button className="btn-ghost h-9 px-3 text-sm" onClick={cancel} disabled={saving}>
                Cancel
              </button>
              <button className="btn-primary h-9" onClick={save} disabled={saving}>
                {saving ? "Saving…" : "Save changes"}
              </button>
            </>
          ) : (
            <button className="btn-primary h-9" onClick={startEdit}>
              Edit content
            </button>
          )}
        </div>
      </div>
      {saveErr && <Banner tone="error" title="Couldn't save">{saveErr}</Banner>}

      <Panel eyebrow="Common to all participants" title="Shared world">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field
            label="Allocation Room"
            value={c.allocation_room_data}
            editing={editing}
            onChange={(v) => set(["common_data", "allocation_room_data"], v)}
          />
          <Field
            label="Business landscape"
            value={c.business_landscape}
            editing={editing}
            onChange={(v) => set(["common_data", "business_landscape"], v)}
          />
          <div>
            <div className="eyebrow mb-1">Business priorities</div>
            {editing ? (
              <div className="space-y-3">
                {c.business_priorities.map((p, i) =>
                  typeof p === "string" ? (
                    <input
                      key={i}
                      className="input w-full text-sm"
                      value={p}
                      onChange={(e) => set(["common_data", "business_priorities", i], e.target.value)}
                    />
                  ) : (
                    <div key={i} className="rounded-xl border border-line p-3">
                      <input
                        className="input w-full text-sm font-medium"
                        value={p.title}
                        onChange={(e) =>
                          set(["common_data", "business_priorities", i, "title"], e.target.value)
                        }
                      />
                      <div className="mt-2 space-y-1">
                        {(p.table ?? []).map((row, j) => (
                          <div key={j} className="flex gap-2">
                            <input
                              className="input w-1/2 text-xs"
                              value={row.item}
                              onChange={(e) =>
                                set(
                                  ["common_data", "business_priorities", i, "table", j, "item"],
                                  e.target.value,
                                )
                              }
                            />
                            <input
                              className="input w-1/2 text-xs"
                              value={row.value}
                              onChange={(e) =>
                                set(
                                  ["common_data", "business_priorities", i, "table", j, "value"],
                                  e.target.value,
                                )
                              }
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  ),
                )}
              </div>
            ) : (
              <ol className="list-decimal space-y-3 pl-5 text-sm text-ink">
                {c.business_priorities.map((p, i) =>
                  typeof p === "string" ? (
                    <li key={i}>{p}</li>
                  ) : (
                    <li key={i}>
                      <div className="font-medium">{p.title}</div>
                      {(p.table ?? []).length > 0 && (
                        <table className="mt-1 w-full max-w-md text-xs">
                          <tbody>
                            {(p.table ?? []).map((row, j) => (
                              <tr key={j} className="border-b border-line last:border-0">
                                <td className="py-1 pr-3 text-muted">{row.item}</td>
                                <td className="py-1 font-medium">{row.value}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      )}
                    </li>
                  ),
                )}
              </ol>
            )}
          </div>
          <Field
            label="Crisis"
            value={c.crisis_data}
            editing={editing}
            onChange={(v) => set(["common_data", "crisis_data"], v)}
          />
          <Field
            label="Reflection board support"
            value={c.reflection_board_helping_data}
            editing={editing}
            onChange={(v) => set(["common_data", "reflection_board_helping_data"], v)}
          />
        </div>
      </Panel>

      {c.reflection_spec && (
        <Panel eyebrow="Teaching frame (hidden from participants)" title="Reflection spec">
          <div className="mb-3 grid gap-3 sm:grid-cols-2">
            <div>
              <div className="eyebrow mb-1">Framework</div>
              <div className="text-sm font-medium">{c.reflection_spec.framework_name}</div>
              <div className="mt-0.5 text-sm text-muted">
                {c.reflection_spec.framework_definition}
              </div>
            </div>
            <div>
              <div className="eyebrow mb-1">Learning tension</div>
              <div className="text-sm">{c.reflection_spec.learning_tension}</div>
            </div>
          </div>
          <div className="eyebrow mb-1.5">Outcome parameters</div>
          <div className="grid gap-3 sm:grid-cols-2">
            {c.reflection_spec.outcome_parameters.map((op) => (
              <div key={op.key} className="rounded-xl border border-line p-3">
                <div className="mb-1 flex items-center gap-2">
                  <span className="rounded-full bg-petrol-soft px-2 py-0.5 text-[11px] font-semibold text-petrol">
                    {op.name}
                  </span>
                  <span className="num text-[11px] text-faint">{op.key}</span>
                </div>
                <div className="text-sm text-muted">{op.definition}</div>
                <div className="mt-1 text-xs text-faint">
                  Strong performer: {op.what_good_looks_like}
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {c.type_set && (
        <Panel
          eyebrow="Decision stances (hidden from participants)"
          title="Type-set (dynamic)"
        >
          <div className="mb-3">
            <div className="eyebrow mb-1">Inferred category</div>
            <div className="text-sm">{c.type_set.inferred_category}</div>
          </div>
          <div className="mb-3">
            <div className="eyebrow mb-1">Learning tension</div>
            <div className="text-sm">{c.type_set.learning_tension}</div>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {c.type_set.stances.map((st, i) => (
              <div key={st.key} className="rounded-xl border border-line p-3">
                <div className="mb-1 flex items-center gap-2">
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[11px] font-semibold",
                      STANCE_STYLES[i % STANCE_STYLES.length],
                    )}
                  >
                    {st.label}
                  </span>
                  <span className="num text-[11px] text-faint">{st.key}</span>
                </div>
                <div className="text-sm text-muted">{st.definition}</div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {ps && !c.type_set && (
        <Panel eyebrow="Decision stances (hidden from participants)" title="Stance scheme">
          <div className="mb-3">
            <div className="eyebrow mb-1">Inferred category</div>
            <EditableText
              editing={editing}
              value={ps.inferred_category}
              onChange={(v) => set(["common_data", "posture_scheme", "inferred_category"], v)}
              long={false}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                ["Protect", "protect_label", "protect_definition"],
                ["Enable", "enable_label", "enable_definition"],
                ["Hybrid", "hybrid_label", "hybrid_definition"],
                ["Defer", "defer_label", "defer_definition"],
              ] as [Posture, keyof PostureScheme, keyof PostureScheme][]
            ).map(([key, labelKey, defKey]) => (
              <div key={key} className="rounded-xl border border-line p-3">
                <div className="mb-1 flex items-center gap-2">
                  {editing ? (
                    <input
                      className="input w-full text-xs font-semibold"
                      value={ps[labelKey] as string}
                      onChange={(e) =>
                        set(["common_data", "posture_scheme", labelKey], e.target.value)
                      }
                    />
                  ) : (
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-[11px] font-semibold",
                        POSTURE_STYLE[key],
                      )}
                    >
                      {ps[labelKey] as string}
                    </span>
                  )}
                  <span className="num text-[11px] text-faint">{key}</span>
                </div>
                <EditableText
                  editing={editing}
                  value={ps[defKey] as string}
                  onChange={(v) => set(["common_data", "posture_scheme", defKey], v)}
                />
              </div>
            ))}
          </div>
        </Panel>
      )}

      {Object.entries(view.rounds).map(([k, r]) => (
        <RoundBlock key={k} roundKey={k} round={r} scheme={ps} typeSet={c.type_set} editing={editing} set={set} />
      ))}
    </div>
  );
}
