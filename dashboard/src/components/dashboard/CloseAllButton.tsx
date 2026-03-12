"use client";

import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { closeAllPositions } from "@/lib/api";

export function CloseAllButton() {
  const [open, setOpen] = useState(false);

  const handleConfirm = async () => {
    try {
      await closeAllPositions();
      toast.success("All positions closed");
    } catch {
      toast.error("Failed to close positions");
    }
    setOpen(false);
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="rounded-lg border border-[var(--color-pnl-negative)] px-4 py-2 text-sm font-medium text-[var(--color-pnl-negative)] transition-colors hover:bg-[var(--color-pnl-negative)]/10"
        aria-label="Close all open positions"
      >
        Close All Positions
      </button>
      <ConfirmDialog
        open={open}
        onConfirm={handleConfirm}
        onCancel={() => setOpen(false)}
        title="Close All Positions"
        description="This will close all open positions at market price. This action cannot be undone."
        confirmLabel="Close All"
        variant="danger"
        countdownSeconds={3}
      />
    </>
  );
}
