"use client";

import { Loader2 } from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface ModelSelectProps {
  value: string | null;
  options: string[];
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
  const hasOptions = options.length > 0;

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
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" aria-hidden /> : null}
    </div>
  );
}
