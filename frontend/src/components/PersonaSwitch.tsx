import type { Persona } from "../types";

/** The one piece of chrome that earns its place: switching buyer is the thesis. */
export function PersonaSwitch({
  personas,
  active,
  onChange,
}: {
  personas: Persona[];
  active: string;
  onChange: (key: string) => void;
}) {
  return (
    <nav className="personas" aria-label="Buyer profile">
      {personas.map((persona) => (
        <button
          key={persona.key}
          className={persona.key === active ? "persona on" : "persona"}
          onClick={() => onChange(persona.key)}
          aria-pressed={persona.key === active}
        >
          {persona.label}
        </button>
      ))}
    </nav>
  );
}
