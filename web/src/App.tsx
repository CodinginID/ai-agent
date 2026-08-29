import { useEffect, type ReactNode } from "react";
import { TopBar } from "./ui/TopBar";
import { RoomCanvas } from "./room/RoomCanvas";
import { InspectorPanel } from "./ui/InspectorPanel";
import { Roster } from "./ui/Roster";
import { ApprovalQueue } from "./ui/ApprovalQueue";
import { ActivityFeed } from "./ui/ActivityFeed";
import { startRoomStream } from "./net/roomStream";
import { setBadge, syncTokenToSw } from "./net/push";
import { useStore } from "./state/store";
import { useIsMobile } from "./hooks/useIsMobile";
import { MobileShell } from "./ui/mobile/MobileShell";

function Section({
  title,
  children,
  grow,
}: {
  title: string;
  children: ReactNode;
  grow?: boolean;
}): JSX.Element {
  return (
    <section
      className={`border-b border-line px-[15px] py-[13px] ${grow ? "flex-1" : ""}`}
    >
      <h2 className="m-0 mb-[11px] font-display text-[11px] font-semibold uppercase tracking-[1.3px] text-ink-faint">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function App(): JSX.Element {
  const isMobile = useIsMobile();

  useEffect(() => {
    const stream = startRoomStream();
    // Token bisa berubah (login ulang) → selalu sinkron ke SW saat app dibuka
    // supaya tombol Setujui/Tolak di notifikasi pakai token yang valid.
    void syncTokenToSw();
    return () => stream.stop();
  }, []);

  // App badge (ikon di homescreen/taskbar) = jumlah approval pending —
  // sinyal "perlu perhatian" tanpa buka tab, sinkron dgn ApprovalQueue.
  // Store plain (tanpa middleware subscribeWithSelector) → subscribe manual
  // & bandingkan panjang sebelumnya sendiri supaya tak spam setBadge tiap tick.
  useEffect(() => {
    let last = useStore.getState().serverApprovals.length;
    setBadge(last);
    return useStore.subscribe((s) => {
      const n = s.serverApprovals.length;
      if (n !== last) {
        last = n;
        setBadge(n);
      }
    });
  }, []);

  if (isMobile) {
    return <MobileShell />;
  }

  return (
    <div className="flex min-h-[100dvh] flex-col md:grid md:h-[100dvh] md:min-h-0 md:grid-cols-[1fr_minmax(300px,348px)] md:grid-rows-[auto_1fr] md:overflow-hidden">
      <div className="md:col-span-2">
        <TopBar />
      </div>

      <main className="relative h-[56vh] min-h-[340px] overflow-hidden bg-bg md:h-auto md:min-h-0">
        <RoomCanvas />
      </main>

      <aside className="scroll-thin flex flex-col border-t border-line bg-panel md:overflow-y-auto md:overflow-x-hidden md:border-l md:border-t-0">
        <Section title="Inspektur Agen">
          <InspectorPanel />
        </Section>
        <Section title="Roster Pasukan">
          <Roster />
        </Section>
        <Section title="Perlu Persetujuan">
          <ApprovalQueue />
        </Section>
        <Section title="Aktivitas Langsung" grow>
          <ActivityFeed />
        </Section>
      </aside>
    </div>
  );
}
