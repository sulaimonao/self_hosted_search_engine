"use client";

import { Loader2 } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export interface ModelSelectOption {
  value: string;
  label?: string;
  description?: string;
  available?: boolean;
}

interface ModelSelectProps {
  value: string | null;
  options: Array<string | ModelSelectOption>;
  onChange: (value: string) => void;
  disabled?: boolean;
  loading?: boolean;
  placeholder?: string;
  id?: string;
}

export function ModelSelect({
  value,
  options,
  onChange,
  disabled = false,
  loading = false,
  placeholder = "Select model",
  id,
}: ModelSelectProps) {
  const normalizedOptions = options.reduce<ModelSelectOption[]>((acc, option) => {
    if (typeof option === "string") {
      acc.push({ value: option, label: option, available: true });
      return acc;
    }
    const normalizedValue = option.value?.trim();
    if (!normalizedValue) {
      return acc;
    }
    acc.push({
      value: normalizedValue,
      label: option.label ?? option.value,
      description:
        option.description ??
        (option.available === false ? "Not installed locally" : undefined),
      available: option.available !== false,
    });
    return acc;
  }, []);

  const hasOptions = normalizedOptions.length > 0;

  return (
    <div className="flex items-center gap-2">
      <Select
        value={value ?? undefined}
        onValueChange={onChange}
        disabled={disabled || !hasOptions}
      >
        <SelectTrigger id={id} className="h-8 w-48">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          {normalizedOptions.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              <div className="flex flex-col">
                <span className="flex items-center gap-2">
                  {option.label ?? option.value}
                  {option.available === false ? (
                    <span className="text-[10px] uppercase tracking-wide text-destructive/80">
                      Unavailable
                    </span>
                  ) : null}
                </span>
                {option.description ? (
                  <span className="text-xs text-muted-foreground">{option.description}</span>
                ) : null}
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" aria-hidden /> : null}
    </div>
  );
}
