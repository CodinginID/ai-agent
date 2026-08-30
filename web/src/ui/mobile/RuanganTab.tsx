import { useEffect, useRef } from "react";
import { RoomCanvas } from "../../room/RoomCanvas";
import { mix } from "../../room/engine/render";
import { ROLE, STATUS } from "../../room/engine/scene";
import { useStore } from "../../state/store";

/** Tab Ruangan mobile: RoomCanvas penuh + kartu status manajer mengambang di
 *  atas hint bawaan RoomCanvas (bottom-3) supaya tak tumpang tindih.
 *
 *  Scene aktif (landscape/portrait) mengikuti orientasi kontainer tab ini —
 *  bukan sekadar "selalu portrait di mobile" — supaya HP landscape / tablet
 *  (yang juga lewat MobileShell) tetap memakai world landscape yang sudah
 *  pas untuk layar lebar. Desktop (App.tsx, RoomCanvas langsung) tak pernah
 *  memanggil applyLayout sama sekali. */
export function RuanganTab(): JSX.Element {
  const manager = useStore((s) => s.agents.find((a) => a.role === "manager") ?? null);

  const st = manager ? STATUS[manager.state] ?? STATUS.idle : null;
  const wrapRef = useRef<HTMLDivElement>(null);
  // true begitu kontainer ini pernah beralih ke portrait — cuma revert ke
  // landscape saat unmount kalau kita yang tadi mengubahnya.
  const switchedToPortrait = useRef(false);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const apply = (): void => {
      const rect = el.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return;
      const portrait = rect.height > rect.width;
      switchedToPortrait.current = portrait;
      useStore.getState().applyLayout(portrait ? "portrait" : "landscape");
    };
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (switchedToPortrait.current) useStore.getState().applyLayout("landscape");
    };
  }, []);

  return (
    <div ref={wrapRef} className="relative h-full w-full">
      <RoomCanvas hideHint />
      {manager && (
        <div className="pointer-events-none absolute inset-x-3 bottom-3 rounded-xl border border-line bg-[var(--c-namebg)] px-3 py-2.5 backdrop-blur">
          <div className="flex items-center gap-2.5">
            <span
              className="grid h-7 w-7 flex-none place-items-center rounded-full text-[14px]"
              style={{ background: mix(ROLE.manager.color, "#ffffff", 0.16) }}
            >
              {ROLE.manager.icon}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12.5px] font-semibold text-ink">
                {manager.name} · {st?.txt}
              </div>
              <div className="truncate text-[11px] text-ink-soft">
                {manager.task ? manager.task.desc : "Belum ada tugas"}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
