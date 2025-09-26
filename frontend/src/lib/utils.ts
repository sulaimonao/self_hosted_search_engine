<<<<<<< ours
<<<<<<< ours
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
=======
=======
>>>>>>> theirs
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function isProbablyUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return Boolean(url.protocol.startsWith("http"));
  } catch (error) {
    return false;
  }
}

export function toRelativeTime(date: Date) {
  const diff = Date.now() - date.getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
<<<<<<< ours
>>>>>>> theirs
=======
>>>>>>> theirs
}
