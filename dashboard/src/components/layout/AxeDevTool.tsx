"use client";

import { useEffect } from "react";
import React from "react";

export function AxeDevTool() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "development") return;

    import("react-dom").then((ReactDOM) => {
      // @ts-expect-error -- @axe-core/react is an optional peer dependency
      import("@axe-core/react").then((axe: { default: CallableFunction }) => {
        axe.default(React, ReactDOM, 1000);
      }).catch(() => {
        // not installed, skip
      });
    });
  }, []);

  return null;
}
