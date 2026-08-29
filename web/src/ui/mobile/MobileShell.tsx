import { useEffect, useRef, useState } from "react";
import { useStore } from "../../state/store";
import { ActivityFeed } from "../ActivityFeed";
import { ApprovalQueue } from "../ApprovalQueue";
import { ApprovalSheet } from "./ApprovalSheet";
import { MobileCommandBar } from "./MobileCommandBar";
import { MobileHeader } from "./MobileHeader";
import { PasukanTab } from "./PasukanTab";
import { RuanganTab } from "./RuanganTab";
import { TabBar, type TabKey } from "./TabBar";

const TAB_STORAGE_KEY = "octopus-mobile-tab";
const TAB_KEYS: TabKey[] = ["ruangan", "persetujuan", "aktivitas", "pasukan"];

function loadTab(): TabKey {
  try {
    const v = window.localStorage.getItem(TAB_STORAGE_KEY);
    if (v && (TAB_KEYS as string[]).includes(v)) return v as TabKey;
  } catch {
    /* localStorage tak tersedia (mode privat, dll) — abaikan */
  }
  return "ruangan";
}

function saveTab(tab: TabKey): void {
  try {
    window.localStorage.setItem(TAB_STORAGE_KEY, tab);
  } catch {
    /* abaikan */
  }
}

/** Shell aplikasi mobile (viewport < md) — header ringkas, konten tab penuh
 *  tinggi, command bar + tab bar sticky di bawah. Dipilih App.tsx via
 *  useIsMobile; layout desktop (grid TopBar/RoomCanvas/aside) tak disentuh. */
export function MobileShell(): JSX.Element {
  const [tab, setTab] = useState<TabKey>(loadTab);
  const [approvalSheetOpen, setApprovalSheetOpen] = useState(false);
  const serverApprovals = useStore((s) => s.serverApprovals);
  const approvals = useStore((s) => s.approvals);
  const approvalCount = serverApprovals.length + approvals.length;

  // Buka sheet persetujuan otomatis begitu approval.request baru masuk,
  // di tab manapun user sedang berada.
  const prevServerLen = useRef(serverApprovals.length);
  useEffect(() => {
    if (serverApprovals.length > prevServerLen.current) {
      setApprovalSheetOpen(true);
      navigator.vibrate?.(30);
    }
    prevServerLen.current = serverApprovals.length;
  }, [serverApprovals.length]);

  const changeTab = (t: TabKey): void => {
    setTab(t);
    saveTab(t);
  };

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden bg-bg">
      <MobileHeader />

      <main className="min-h-0 flex-1 overflow-hidden">
        {tab === "ruangan" && <RuanganTab />}
        {tab === "persetujuan" && (
          <div className="scroll-thin h-full overflow-y-auto px-3 py-3">
            <ApprovalQueue />
          </div>
        )}
        {tab === "aktivitas" && (
          <div className="scroll-thin h-full overflow-y-auto px-3 py-3">
            <ActivityFeed />
          </div>
        )}
        {tab === "pasukan" && <PasukanTab />}
      </main>

      <MobileCommandBar />
      <TabBar active={tab} onChange={changeTab} approvalCount={approvalCount} />

      {approvalSheetOpen && (
        <ApprovalSheet onClose={() => setApprovalSheetOpen(false)} />
      )}
    </div>
  );
}
