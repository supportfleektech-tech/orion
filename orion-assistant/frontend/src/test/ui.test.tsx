import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Badge, Bar, Counter, Gauge, Modal, Sparkline, Toast, Toggle, bytes, riskTone, timeAgo } from "../components/ui";

describe("Counter", () => {
  it("lands on the exact value rather than near it", async () => {
    render(<Counter value={893} duration={40} />);
    await waitFor(() => expect(screen.getByText("893")).toBeInTheDocument());
  });

  it("formats through the supplied formatter", async () => {
    render(<Counter value={0.5} duration={40} format={(n) => `${Math.round(n * 100)}%`} />);
    await waitFor(() => expect(screen.getByText("50%")).toBeInTheDocument());
  });
});

describe("Toggle", () => {
  it("reports the new state when clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Toggle checked={false} onChange={onChange} label="Web search" />);

    await user.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("reflects the checked state it is given", () => {
    render(<Toggle checked onChange={() => {}} label="On" />);
    expect(screen.getByRole("checkbox")).toBeChecked();
  });
});

describe("Modal", () => {
  it("renders nothing when closed", () => {
    render(<Modal open={false} onClose={() => {}} title="Hi">body</Modal>);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Modal open onClose={onClose} title="Run trace">body</Modal>);

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("closes when the backdrop is clicked but not the panel", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Modal open onClose={onClose} title="Run trace">body</Modal>);

    await user.click(screen.getByText("body"));
    expect(onClose).not.toHaveBeenCalled();

    await user.click(document.querySelector(".modal-backdrop")!);
    expect(onClose).toHaveBeenCalled();
  });
});

describe("Toast", () => {
  it("announces itself to screen readers", () => {
    render(<Toast toast={{ kind: "ok", text: "Saved" }} />);
    const toast = screen.getByRole("status");
    expect(toast).toHaveTextContent("Saved");
    expect(toast).toHaveAttribute("aria-live", "polite");
  });

  it("renders nothing when there is no toast", () => {
    render(<Toast toast={null} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("Sparkline", () => {
  it("needs at least two points to mean anything", () => {
    const { container } = render(<Sparkline values={[5]} />);
    expect(container.querySelector("svg")).toBeNull();
  });

  it("draws a path through the values", () => {
    const { container } = render(<Sparkline values={[1, 5, 3, 9]} />);
    const path = container.querySelector("path[stroke]");
    expect(path).toBeTruthy();
    expect(path!.getAttribute("d")).toMatch(/^M[\d.]+,[\d.]+ L/);
  });

  it("survives a flat series without dividing by zero", () => {
    const { container } = render(<Sparkline values={[4, 4, 4]} />);
    expect(container.querySelector("path[stroke]")!.getAttribute("d")).not.toMatch(/NaN/);
  });
});

describe("Gauge and Bar", () => {
  it("clamps the bar to 0-100 rather than overflowing", () => {
    const { container } = render(<Bar value={150} />);
    expect((container.querySelector(".bar > i") as HTMLElement).style.width).toBe("100%");
  });

  it("clamps negatives to zero", () => {
    const { container } = render(<Bar value={-20} />);
    expect((container.querySelector(".bar > i") as HTMLElement).style.width).toBe("0%");
  });

  it("exposes the bar's value to assistive tech", () => {
    render(<Bar value={42} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "42");
  });

  it("renders a gauge arc", () => {
    const { container } = render(<Gauge value={0.75} />);
    expect(container.querySelectorAll("circle")).toHaveLength(2);
  });
});

describe("Badge", () => {
  it("carries its tone as a class so status reads at a glance", () => {
    const { container } = render(<Badge tone="err">failed</Badge>);
    expect(container.querySelector(".badge.err")).toBeTruthy();
  });
});

describe("helpers", () => {
  it("maps risk tiers to tones, with destructive as the loudest", () => {
    expect(riskTone("destructive")).toBe("err");
    expect(riskTone("high")).toBe("warn");
    expect(riskTone("medium")).toBe("info");
    expect(riskTone("low")).toBe("ok");
  });

  it("formats bytes at each magnitude", () => {
    expect(bytes(512)).toBe("512 B");
    expect(bytes(2048)).toBe("2.0 KB");
    expect(bytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });

  it("renders relative times", () => {
    expect(timeAgo(null)).toBe("—");
    expect(timeAgo(new Date().toISOString())).toBe("just now");
    expect(timeAgo(new Date(Date.now() - 5 * 60_000).toISOString())).toBe("5m ago");
    expect(timeAgo(new Date(Date.now() - 3 * 3_600_000).toISOString())).toBe("3h ago");
    expect(timeAgo(new Date(Date.now() - 2 * 86_400_000).toISOString())).toBe("2d ago");
  });
});
