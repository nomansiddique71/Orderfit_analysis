import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";

/**
 * Scroll state for a horizontal, scroll-snapping carousel (pure UI behaviour).
 * The track is a normal scroll container, so touch swipe and trackpad scrolling work natively;
 * this hook adds previous/next, jump-to-card, arrow-key support and the current position.
 */
export function useCarousel(count: number) {
  const track = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const [edges, setEdges] = useState({ start: true, end: count <= 1 });

  const cards = () => Array.from(track.current?.children ?? []) as HTMLElement[];

  const measure = useCallback(() => {
    const el = track.current;
    if (!el) return;
    const items = Array.from(el.children) as HTMLElement[];
    const left = el.scrollLeft + el.offsetLeft;
    let best = 0, dist = Infinity;
    items.forEach((c, i) => { const d = Math.abs(c.offsetLeft - left); if (d < dist) { dist = d; best = i; } });
    // At the far right, the last card counts as current even if it can't snap to the left edge.
    const atEnd = el.scrollLeft + el.clientWidth >= el.scrollWidth - 4;
    setIndex(atEnd ? items.length - 1 : best);
    setEdges({ start: el.scrollLeft <= 4, end: atEnd });
  }, []);

  useEffect(() => {
    const el = track.current;
    if (!el) return;
    measure();
    el.addEventListener("scroll", measure, { passive: true });
    window.addEventListener("resize", measure);
    return () => { el.removeEventListener("scroll", measure); window.removeEventListener("resize", measure); };
  }, [measure, count]);

  const goTo = useCallback((i: number) => {
    const el = track.current, c = cards()[Math.max(0, Math.min(count - 1, i))];
    if (!el || !c) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollTo({ left: c.offsetLeft - el.offsetLeft, behavior: reduce ? "auto" : "smooth" });
  }, [count]);

  // Step by real card positions, so "previous" also works from the far end, where
  // the last cards can't snap to the left edge.
  const offsets = () => { const el = track.current; return el ? cards().map((c) => c.offsetLeft - el.offsetLeft) : []; };
  const prev = () => {
    const x = track.current?.scrollLeft ?? 0, o = offsets();
    let i = -1; o.forEach((v, j) => { if (v < x - 4) i = j; });
    goTo(Math.max(0, i));
  };
  const next = () => {
    const x = track.current?.scrollLeft ?? 0, i = offsets().findIndex((v) => v > x + 4);
    goTo(i === -1 ? count - 1 : i);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if ((e.target as HTMLElement).closest("button, a, input") && e.target !== e.currentTarget) return;
    if (e.key === "ArrowRight") { e.preventDefault(); next(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); prev(); }
    else if (e.key === "Home") { e.preventDefault(); goTo(0); }
    else if (e.key === "End") { e.preventDefault(); goTo(count - 1); }
  };

  return { track, index, atStart: edges.start, atEnd: edges.end, prev, next, goTo, onKeyDown };
}
