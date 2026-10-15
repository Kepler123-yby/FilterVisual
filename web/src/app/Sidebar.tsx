import { useLayoutEffect, useRef } from "react";
import type { ReactNode } from "react";

export default function Sidebar({
  className,
  children,
}: {
  className: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLElement>(null);

  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    let frame: number | null = null;

    function measure() {
      if (!element) return;
      const top = Math.max(15, element.getBoundingClientRect().top);
      const maxHeight = `${Math.max(0, window.innerHeight - top - 15)}px`;
      if (element.style.getPropertyValue("--sidebar-max-height") !== maxHeight)
        element.style.setProperty("--sidebar-max-height", maxHeight);
    }

    function scheduleMeasure() {
      if (frame !== null) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        measure();
      });
    }

    measure();
    window.addEventListener("scroll", scheduleMeasure, { passive: true });
    window.addEventListener("resize", scheduleMeasure, { passive: true });
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(scheduleMeasure);
    observer?.observe(element);
    observer?.observe(document.body);

    return () => {
      window.removeEventListener("scroll", scheduleMeasure);
      window.removeEventListener("resize", scheduleMeasure);
      observer?.disconnect();
      if (frame !== null) cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <aside ref={ref} className={className}>
      {children}
    </aside>
  );
}
