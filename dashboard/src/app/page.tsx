"use client";

import dynamic from "next/dynamic";
import { TopNav } from "@/components/layout/TopNav";
import { KPIHeader } from "@/components/dashboard/KPIHeader";
import BotControlPanel from "@/components/bot/BotControlPanel";
import PositionsTable from "@/components/data/PositionsTable";
import OrderHistoryTable from "@/components/data/OrderHistoryTable";

const CandlestickPanel = dynamic(
  () => import("@/components/chart/CandlestickPanel"),
  { ssr: false },
);

export default function DashboardPage() {
  return (
    <div className="min-h-screen">
      <TopNav />
      <KPIHeader />
      <main className="mx-auto max-w-7xl p-4">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* Chart Area */}
          <div className="lg:col-span-2">
            <CandlestickPanel />
          </div>

          {/* Bot Control Panel */}
          <div>
            <BotControlPanel />
          </div>

          {/* Positions */}
          <div className="lg:col-span-2">
            <PositionsTable />
          </div>

          {/* Order History */}
          <div className="lg:col-span-1">
            <OrderHistoryTable />
          </div>
        </div>
      </main>
    </div>
  );
}
