export const SHARED_LIB_VERSION = "0.1.0";

/**
 * Ratified temporal classes (AD-005 / BR-19). Mirror of the Python `TemporalClass` enum.
 * FR = full bitemporal; IA = immutable append-only; EV = effective-dated versioned.
 */
export type TemporalClass = "FR" | "IA" | "EV";
