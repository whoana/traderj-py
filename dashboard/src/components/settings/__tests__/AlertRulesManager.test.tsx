import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AlertRulesManager } from "../AlertRulesManager";
import type { AlertRule } from "@/types/api";

const mockRules: AlertRule[] = [
  {
    id: "1",
    type: "price_above",
    condition: "gt",
    value: 50000000,
    channel: "slack",
    enabled: true,
    created_at: "2024-01-01",
  },
  {
    id: "2",
    type: "drawdown",
    condition: "lt",
    value: -5,
    channel: "email",
    enabled: false,
    created_at: "2024-01-02",
  },
];

describe("AlertRulesManager", () => {
  it("renders rules list", () => {
    render(
      <AlertRulesManager
        rules={mockRules}
        onToggle={vi.fn()}
        onDelete={vi.fn()}
        onAdd={vi.fn()}
        loading={false}
      />,
    );
    expect(screen.getByText("price_above")).toBeInTheDocument();
    expect(screen.getByText("drawdown")).toBeInTheDocument();
  });

  it("calls onToggle when toggle clicked", async () => {
    const onToggle = vi.fn();
    const { container } = render(
      <AlertRulesManager
        rules={mockRules}
        onToggle={onToggle}
        onDelete={vi.fn()}
        onAdd={vi.fn()}
        loading={false}
      />,
    );
    const toggleButton = container.querySelector(
      'button[aria-label="Toggle rule price_above"]',
    );
    expect(toggleButton).not.toBeNull();
    fireEvent.click(toggleButton!);
    expect(onToggle).toHaveBeenCalledWith("1");
  });

  it("shows confirm dialog on delete", () => {
    render(
      <AlertRulesManager
        rules={mockRules}
        onToggle={vi.fn()}
        onDelete={vi.fn()}
        onAdd={vi.fn()}
        loading={false}
      />,
    );
    const deleteButtons = screen.getAllByText("Delete");
    // Filter to only rule delete buttons (not dialog)
    fireEvent.click(deleteButtons[0]);
    expect(screen.getByText("Delete Alert Rule")).toBeInTheDocument();
  });

  it("shows empty message when no rules", () => {
    render(
      <AlertRulesManager
        rules={[]}
        onToggle={vi.fn()}
        onDelete={vi.fn()}
        onAdd={vi.fn()}
        loading={false}
      />,
    );
    expect(screen.getByText("No alert rules configured")).toBeInTheDocument();
  });
});
