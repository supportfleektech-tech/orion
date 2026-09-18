import type { Transition, Variants } from "framer-motion";

/**
 * Shared motion vocabulary.
 *
 * Importing these rather than hand-writing transitions keeps the whole app
 * moving with one personality. The rules of thumb encoded here:
 *
 * - Entrances travel a short distance (6–14px). Big journeys read as slow.
 * - Exits are faster than entrances; nobody wants to wait for something to go.
 * - Lists stagger, but cap the delay so a long list does not crawl in.
 * - Springs for anything a pointer touches, tweens for ambient motion.
 */

export const EASE = [0.22, 1, 0.36, 1] as const;
export const EASE_OUT = [0.16, 1, 0.3, 1] as const;

export const spring: Transition = { type: "spring", stiffness: 420, damping: 32, mass: 0.7 };
export const springSoft: Transition = { type: "spring", stiffness: 260, damping: 28 };
export const springSnappy: Transition = { type: "spring", stiffness: 600, damping: 30 };

/** Page-level transition, used by the route crossfade. */
export const pageVariants: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.32, ease: EASE } },
  exit: { opacity: 0, y: -6, transition: { duration: 0.16, ease: EASE } },
};

/** Container that reveals its children in sequence. */
export const stagger = (delay = 0.04, initial = 0): Variants => ({
  initial: {},
  animate: {
    transition: { staggerChildren: delay, delayChildren: initial },
  },
});

/** The child half of `stagger`. */
export const riseIn: Variants = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.4, ease: EASE } },
};

export const fadeIn: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.3, ease: EASE } },
  exit: { opacity: 0, transition: { duration: 0.15 } },
};

export const scaleIn: Variants = {
  initial: { opacity: 0, scale: 0.96 },
  animate: { opacity: 1, scale: 1, transition: spring },
  exit: { opacity: 0, scale: 0.97, transition: { duration: 0.12 } },
};

/** Rows that can be added or removed — list items, toasts, results. */
export const rowVariants: Variants = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.3, ease: EASE } },
  exit: { opacity: 0, x: -10, transition: { duration: 0.16, ease: EASE } },
};

/** Modals and dialogs. */
export const modalVariants: Variants = {
  initial: { opacity: 0, scale: 0.94, y: 14 },
  animate: { opacity: 1, scale: 1, y: 0, transition: spring },
  exit: { opacity: 0, scale: 0.97, y: 8, transition: { duration: 0.14, ease: EASE } },
};

export const backdropVariants: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.2 } },
  exit: { opacity: 0, transition: { duration: 0.15 } },
};

/** Panels that expand in place, e.g. an accordion body. */
export const collapseVariants: Variants = {
  initial: { height: 0, opacity: 0 },
  animate: {
    height: "auto",
    opacity: 1,
    transition: { height: { duration: 0.26, ease: EASE }, opacity: { duration: 0.2, delay: 0.06 } },
  },
  exit: {
    height: 0,
    opacity: 0,
    transition: { height: { duration: 0.2, ease: EASE }, opacity: { duration: 0.1 } },
  },
};

/** Interactive feedback for buttons and cards. */
export const tap = { scale: 0.975 };
export const liftHover = { y: -2, transition: spring };
