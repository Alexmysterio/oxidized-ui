import { useEffect, useState } from "react";

import { Input } from "@/components/ui/input";

export function HookNameInput({
  name,
  onRename,
  ariaLabel,
}: {
  name: string;
  onRename: (next: string) => void;
  ariaLabel: string;
}) {
  const [value, setValue] = useState(name);
  useEffect(() => setValue(name), [name]);
  const commit = () => {
    const next = value.trim();
    if (!next || next === name) {
      setValue(name);
      return;
    }
    onRename(next);
  };
  return (
    <Input
      value={value}
      onChange={(event) => setValue(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          commit();
        }
        if (event.key === "Escape") setValue(name);
      }}
      className="h-8 font-mono text-xs"
      aria-label={ariaLabel}
    />
  );
}
