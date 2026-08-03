"use client";

import { motion, useReducedMotion } from "framer-motion";
import { clsx } from "clsx";

export function Stamp({ children, endorse = false }: { children: React.ReactNode; endorse?: boolean }) {
  const reduceMotion = useReducedMotion();
  const restingTransform = `scale(1) rotate(${endorse ? 1.2 : -1.4}deg)`;
  return (
    <motion.span
      className={clsx("stamp", endorse && "endorse")}
      initial={{
        opacity: 0,
        transform: reduceMotion
          ? restingTransform
          : `scale(1.08) rotate(${endorse ? 4 : -4}deg)`,
      }}
      animate={{ opacity: 1, transform: restingTransform }}
      transition={{ duration: .22, ease: [.2, .9, .25, 1] }}
    >
      {children}
    </motion.span>
  );
}
