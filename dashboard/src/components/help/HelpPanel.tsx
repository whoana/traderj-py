"use client";

import { useState, useMemo, useRef, useEffect, useCallback } from "react";
import { helpEntries, FEATURED_IDS, CATEGORY_LABELS, type HelpEntry } from "./helpData";

const PAGE_ENTRIES = helpEntries.filter((e) => e.category === "page");

interface HelpPanelProps {
  open: boolean;
  onClose: () => void;
}

export function HelpPanel({ open, onClose }: HelpPanelProps) {
  const [query, setQuery] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setExpandedId(null);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open, onClose]);

  // Close on ESC
  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  const results = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return null;
    return helpEntries.filter(
      (e) =>
        e.term.toLowerCase().includes(q) ||
        e.termKo.includes(q) ||
        e.description.includes(q) ||
        e.id.includes(q),
    );
  }, [query]);

  const featured = useMemo(
    () => FEATURED_IDS.map((id) => helpEntries.find((e) => e.id === id)).filter(Boolean) as HelpEntry[],
    [],
  );

  const navigateTo = useCallback((id: string) => {
    setExpandedId(id);
    setQuery("");
  }, []);

  if (!open) return null;

  const displayItems = results ?? featured;
  const showingSearch = results !== null;

  return (
    <div
      ref={panelRef}
      className="absolute right-0 top-full mt-1 z-50 w-[calc(100vw-1rem)] sm:w-96 max-h-[70vh] overflow-hidden rounded-lg border border-border bg-bg-card shadow-xl flex flex-col"
    >
      {/* Search */}
      <div className="border-b border-border p-3">
        <div className="relative">
          <svg className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search help... (한국어/English)"
            className="w-full rounded-md border border-border bg-bg-primary py-2 pl-9 pr-3 text-sm text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
        {showingSearch && (
          <p className="mt-1.5 text-[10px] text-text-muted">
            {results.length}개 결과
          </p>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto overscroll-contain">
        {/* Items */}
        {displayItems.length > 0 ? (
          <div className="p-2">
            {!showingSearch && (
              <p className="mb-1.5 px-1 text-[10px] font-medium uppercase tracking-wider text-text-muted">
                Featured
              </p>
            )}
            <div className="space-y-0.5">
              {displayItems.map((entry) => (
                <HelpItem
                  key={entry.id}
                  entry={entry}
                  expanded={expandedId === entry.id}
                  onToggle={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                  onNavigate={navigateTo}
                />
              ))}
            </div>
          </div>
        ) : showingSearch ? (
          <div className="p-6 text-center">
            <p className="text-sm text-text-muted">No results found</p>
            <p className="mt-1 text-[10px] text-text-muted">Try a different keyword</p>
          </div>
        ) : null}

        {/* Page Guide (only when not searching) */}
        {!showingSearch && (
          <div className="border-t border-border/50 p-2">
            <p className="mb-1.5 px-1 text-[10px] font-medium uppercase tracking-wider text-text-muted">
              Pages
            </p>
            <div className="space-y-0.5">
              {PAGE_ENTRIES.map((entry) => (
                <HelpItem
                  key={entry.id}
                  entry={entry}
                  expanded={expandedId === entry.id}
                  onToggle={() => setExpandedId(expandedId === entry.id ? null : entry.id)}
                  onNavigate={navigateTo}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Help Item ── */

function HelpItem({
  entry,
  expanded,
  onToggle,
  onNavigate,
}: {
  entry: HelpEntry;
  expanded: boolean;
  onToggle: () => void;
  onNavigate: (id: string) => void;
}) {
  const cat = CATEGORY_LABELS[entry.category];

  return (
    <div className={`rounded-md transition-colors ${expanded ? "bg-bg-primary" : "hover:bg-bg-hover"}`}>
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-2 py-2 text-left"
      >
        <span className={`shrink-0 text-[9px] font-semibold uppercase ${cat.color}`}>
          {cat.label}
        </span>
        <span className="flex-1 truncate text-sm text-text-primary">{entry.term}</span>
        <span className="shrink-0 text-[10px] text-text-muted">{entry.termKo}</span>
        <svg
          className={`h-3.5 w-3.5 shrink-0 text-text-muted transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="px-2 pb-2">
          <p className="text-xs leading-relaxed text-text-secondary">{entry.description}</p>
          {entry.related && entry.related.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {entry.related.map((rid) => {
                const rel = helpEntries.find((e) => e.id === rid);
                if (!rel) return null;
                return (
                  <button
                    key={rid}
                    onClick={() => onNavigate(rid)}
                    className="rounded bg-bg-hover px-1.5 py-0.5 text-[10px] text-accent hover:bg-accent/10 transition-colors"
                  >
                    {rel.termKo}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
