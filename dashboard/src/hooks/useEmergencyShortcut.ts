import { useEffect } from "react";
import { emergencyStopAll } from "@/lib/api";
import { toast } from "sonner";

export function useEmergencyShortcut() {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === "E") {
        e.preventDefault();
        emergencyStopAll()
          .then(() => toast.success("Emergency stop executed"))
          .catch((err) =>
            toast.error(`Emergency stop failed: ${(err as Error).message}`),
          );
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
}
