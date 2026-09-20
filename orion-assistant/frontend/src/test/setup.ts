import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

/**
 * Shared test environment.
 *
 * jsdom does not implement the browser APIs the UI leans on, so they are
 * stubbed once here rather than in every file. Anything a test actually cares
 * about should be asserted, not stubbed.
 */

afterEach(cleanup);

// Framer Motion measures elements and observes resizes; jsdom does neither.
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

globalThis.IntersectionObserver = class {
  constructor() {}
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return []; }
  root = null;
  rootMargin = "";
  thresholds = [];
} as unknown as typeof IntersectionObserver;

/**
 * Report reduced motion in tests.
 *
 * Framer Motion animates in real time even under jsdom, so exit transitions
 * kept assertions waiting and produced tests that failed roughly one run in
 * four -- always on a timeout, never on the logic. Honouring the same
 * preference a user can set makes transitions instant and the suite
 * deterministic, without stubbing the library itself.
 */
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: query.includes("prefers-reduced-motion"),
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

window.HTMLElement.prototype.scrollIntoView = vi.fn();
