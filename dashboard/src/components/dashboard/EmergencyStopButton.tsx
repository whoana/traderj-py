"use client";

import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { emergencyStopAll } from "@/lib/api";

export function EmergencyStopButton() {
  const [open, setOpen] = useState(false);

  const handleConfirm = async () => {
    try {
      await emergencyStopAll();
      toast.success("All bots stopped");
    } catch {
      toast.error("Emergency stop failed");
    }
    setOpen(false);
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="rounded-lg bg-[var(--color-pnl-negative)] px-4 py-2 text-sm font-bold text-white transition-colors hover:bg-[var(--color-pnl-negative)]/90"
        aria-label="Emergency stop all bots"
      >
        Emergency Stop
      </button>
      <ConfirmDialog
        open={open}
        onConfirm={handleConfirm}
        onCancel={() => setOpen(false)}
        title="Emergency Stop All Bots"
        description="This will immediately stop all running bots and cancel pending orders. This action cannot be undone."
        confirmLabel="Stop All"
        variant="danger"
        countdownSeconds={3}
      />
    </>
  );
}
