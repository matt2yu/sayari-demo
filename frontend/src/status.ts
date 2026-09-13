import type { Status } from "./types";

/** One definition of what each status looks like and is called.
 *
 *  The wording matters as much as the colour: "prohibited" and "diligence
 *  required" are claims about law, and the UI must not soften or inflate them
 *  differently in different places.
 */
export const STATUS = {
  prohibited: {
    label: "Prohibited",
    short: "Prohibited",
    verb: "cannot buy",
    dot: "bg-stop",
    text: "text-stop",
    chip: "text-stop border-stop/45 bg-stop/10",
    edge: "border-l-stop",
    bar: "bg-stop",
  },
  review: {
    label: "Diligence required",
    short: "Check first",
    verb: "must review before buying",
    dot: "bg-check",
    text: "text-check",
    chip: "text-check border-check/45 bg-check/10",
    edge: "border-l-check",
    bar: "bg-check",
  },
  no_restriction: {
    label: "No restriction found",
    short: "Clear",
    verb: "can buy",
    dot: "bg-clear",
    text: "text-clear",
    chip: "text-clear border-clear/30 bg-clear/8",
    edge: "border-l-line",
    bar: "bg-clear",
  },
} satisfies Record<Status, Record<string, string>>;

export const ORDER: Record<Status, number> = {
  prohibited: 0,
  review: 1,
  no_restriction: 2,
};
