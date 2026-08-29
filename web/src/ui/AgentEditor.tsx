import { useState } from "react";
import { useIsMobile } from "../hooks/useIsMobile";
import { deleteAgent, fetchRoster, saveAgent } from "../net/api";
import { ROLE } from "../room/engine/scene";
import { useStore } from "../state/store";
import type { Role } from "../state/types";
import { BottomSheet } from "./mobile/BottomSheet";

const ROLE_OPTIONS: Role[] = [
  "manager",
  "coder",
  "tester",
  "reviewer",
  "deployer",
  "researcher",
];

function slugify(name: string, taken: Set<string>): string {
  const base =
    name
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "agen";
  if (!taken.has(base)) return base;
  let i = 2;
  while (taken.has(`${base}-${i}`)) i += 1;
  return `${base}-${i}`;
}

export interface AgentEditorProps {
  /** null = mode tambah agen baru. */
  agent: { id: string; name: string; role: Role } | null;
  onClose: () => void;
}

/** Editor CRUD roster satu-satunya — muncul sebagai bottom sheet di mobile
 *  (Pasukan tab) dan modal di desktop (tombol "Kelola" di Roster). Optimistic
 *  update ke store dulu, lalu refetch & tampilkan error kalau server menolak. */
export function AgentEditor({ agent, onClose }: AgentEditorProps): JSX.Element {
  const isMobile = useIsMobile();
  const agents = useStore((s) => s.agents);
  const applyRoster = useStore((s) => s.applyRoster);
  const [name, setName] = useState(agent?.name ?? "");
  const [role, setRole] = useState<Role>(agent?.role ?? "coder");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isManager = agent?.role === "manager";

  const rosterList = (): { id: string; name: string; role: Role }[] =>
    agents.map((a) => ({ id: a.id, name: a.name, role: a.role }));

  const revertToServer = async (): Promise<void> => {
    const fresh = await fetchRoster();
    if (fresh) applyRoster(fresh as { id: string; name: string; role: Role }[]);
  };

  const handleSave = async (): Promise<void> => {
    const trimmed = name.trim();
    if (!trimmed || trimmed.length > 24) {
      setError("Nama harus 1–24 karakter");
      return;
    }
    setBusy(true);
    setError(null);

    const id = agent?.id ?? slugify(trimmed, new Set(agents.map((a) => a.id)));
    const list = rosterList();
    const idx = list.findIndex((a) => a.id === id);
    if (idx >= 0) list[idx] = { id, name: trimmed, role };
    else list.push({ id, name: trimmed, role });
    applyRoster(list); // optimistic

    const res = await saveAgent(id, { name: trimmed, role });
    setBusy(false);
    if (!res.ok) {
      setError(res.detail ?? "Gagal menyimpan");
      await revertToServer();
      return;
    }
    onClose();
  };

  const handleDelete = async (): Promise<void> => {
    if (!agent || isManager) return;
    setBusy(true);
    setError(null);

    const list = rosterList().filter((a) => a.id !== agent.id);
    applyRoster(list); // optimistic

    const res = await deleteAgent(agent.id);
    setBusy(false);
    if (!res.ok) {
      setError(res.detail ?? "Gagal menghapus");
      await revertToServer();
      return;
    }
    onClose();
  };

  const content = (
    <div className="flex flex-col gap-3">
      <div>
        <label className="block font-mono text-[11px] uppercase tracking-wide text-ink-faint">
          Nama
        </label>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={24}
          placeholder="Nama agen"
          className="mt-1 w-full rounded-lg border border-line bg-surface-2 px-3 py-2.5 text-[14px] text-ink outline-none focus-visible:border-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent"
        />
      </div>

      <div>
        <label className="block font-mono text-[11px] uppercase tracking-wide text-ink-faint">
          Peran
        </label>
        <div className="mt-1.5 grid grid-cols-3 gap-1.5">
          {ROLE_OPTIONS.map((r) => {
            const active = r === role;
            return (
              <button
                key={r}
                type="button"
                onClick={() => setRole(r)}
                className="min-h-[40px] rounded-lg border px-2 text-[12px] font-semibold transition"
                style={{
                  borderColor: active ? ROLE[r].color : "var(--line)",
                  color: active ? ROLE[r].color : "var(--ink-soft)",
                  background: active
                    ? `color-mix(in oklab, ${ROLE[r].color} 14%, var(--panel))`
                    : "transparent",
                }}
              >
                {ROLE[r].icon} {ROLE[r].label}
              </button>
            );
          })}
        </div>
      </div>

      {error && <p className="text-[12px] text-st-error">{error}</p>}

      <div className="mt-1 flex gap-2">
        <button
          type="button"
          onClick={() => void handleSave()}
          disabled={busy}
          className="min-h-[44px] flex-1 rounded-lg bg-accent text-[13px] font-semibold text-accent-ink transition disabled:opacity-60"
        >
          Simpan
        </button>
        <button
          type="button"
          onClick={() => void handleDelete()}
          disabled={busy || !agent || isManager}
          title={isManager ? "Manajer tidak bisa dihapus" : undefined}
          className="min-h-[44px] flex-1 rounded-lg border border-line text-[13px] font-semibold text-ink transition disabled:opacity-40"
        >
          Hapus
        </button>
        <button
          type="button"
          onClick={onClose}
          className="min-h-[44px] flex-1 rounded-lg border border-line text-[13px] font-semibold text-ink-soft"
        >
          Batal
        </button>
      </div>
      {isManager && (
        <p className="-mt-1.5 text-[11px] text-ink-faint">
          Manajer tidak bisa dihapus — harus ada tepat satu manajer.
        </p>
      )}
    </div>
  );

  const title = agent ? "Ubah agen" : "Tambah agen";

  if (isMobile) {
    return (
      <BottomSheet onClose={onClose} title={title}>
        {content}
      </BottomSheet>
    );
  }

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-line bg-surface p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="m-0 mb-3 font-display text-[16px] font-bold text-ink">{title}</h2>
        {content}
      </div>
    </div>
  );
}
