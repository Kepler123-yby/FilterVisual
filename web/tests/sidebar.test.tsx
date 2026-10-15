import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import Sidebar from "../src/app/Sidebar";

let top = 181.5;
let nextFrame = 0;
const frames = new Map<number, FrameRequestCallback>();
const observers: MockResizeObserver[] = [];

class MockResizeObserver {
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();

  constructor(private callback: ResizeObserverCallback) {
    observers.push(this);
  }

  notify() {
    this.callback([], this as unknown as ResizeObserver);
  }
}

function flushFrame() {
  act(() => {
    const callbacks = [...frames.values()];
    frames.clear();
    callbacks.forEach((callback) => callback(0));
  });
}

function setup() {
  const view = render(
    <Sidebar className="filter-sidebar">
      <p>滤波器设置</p>
    </Sidebar>,
  );
  const sidebar = screen.getByRole("complementary");
  return {
    ...view,
    sidebar,
    maxHeight: () => sidebar.style.getPropertyValue("--sidebar-max-height"),
  };
}

beforeEach(() => {
  top = 181.5;
  nextFrame = 0;
  frames.clear();
  observers.length = 0;
  vi.stubGlobal("innerHeight", 720);
  vi.stubGlobal("ResizeObserver", MockResizeObserver);
  vi.stubGlobal(
    "requestAnimationFrame",
    vi.fn((callback: FrameRequestCallback) => {
      frames.set(++nextFrame, callback);
      return nextFrame;
    }),
  );
  vi.stubGlobal(
    "cancelAnimationFrame",
    vi.fn((id: number) => frames.delete(id)),
  );
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(
    () =>
      ({
        top,
        bottom: top + 600,
        left: 0,
        right: 306,
        width: 306,
        height: 600,
        x: 0,
        y: top,
        toJSON: () => ({}),
      }) as DOMRect,
  );
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("sidebar viewport height", () => {
  it("keeps the initial sidebar bottom inside the viewport", () => {
    const { sidebar, maxHeight } = setup();
    expect(sidebar).toHaveClass("filter-sidebar");
    expect(sidebar).toHaveTextContent("滤波器设置");
    expect(maxHeight()).toBe("523.5px");
    expect(top + Number.parseFloat(maxHeight())).toBe(705);
    expect(observers[0].observe).toHaveBeenCalledWith(sidebar);
    expect(observers[0].observe).toHaveBeenCalledWith(document.body);
  });

  it("grows to the sticky height after page scrolling and coalesces updates", () => {
    const { maxHeight } = setup();
    top = 15;
    fireEvent.scroll(window);
    fireEvent.scroll(window);
    fireEvent.resize(window);
    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);
    expect(maxHeight()).toBe("523.5px");
    flushFrame();
    expect(maxHeight()).toBe("690px");
  });

  it("responds to viewport resizing without imposing a minimum height", () => {
    const { maxHeight } = setup();
    vi.stubGlobal("innerHeight", 250);
    fireEvent.resize(window);
    flushFrame();
    expect(maxHeight()).toBe("53.5px");
    vi.stubGlobal("innerHeight", 180);
    fireEvent.resize(window);
    flushFrame();
    expect(maxHeight()).toBe("0px");
  });

  it("remeasures after layout changes and only writes a changed height", () => {
    const { sidebar, maxHeight } = setup();
    const setProperty = vi.spyOn(sidebar.style, "setProperty");
    observers[0].notify();
    flushFrame();
    expect(setProperty).not.toHaveBeenCalled();
    top = 230;
    observers[0].notify();
    flushFrame();
    expect(maxHeight()).toBe("475px");
    expect(setProperty).toHaveBeenCalledTimes(1);
  });

  it("disconnects measurements and cancels a queued frame on unmount", () => {
    const { unmount } = setup();
    fireEvent.scroll(window);
    expect(frames.size).toBe(1);
    unmount();
    expect(observers[0].disconnect).toHaveBeenCalledOnce();
    expect(cancelAnimationFrame).toHaveBeenCalledWith(1);
    expect(frames.size).toBe(0);
    fireEvent.scroll(window);
    fireEvent.resize(window);
    expect(requestAnimationFrame).toHaveBeenCalledTimes(1);
  });
});
