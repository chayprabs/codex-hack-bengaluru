const FIXED_LOCALE = "en-GB";
const FIXED_TIME_ZONE = "UTC";

export function formatDateTime(value: string | Date | null | undefined) {
  if (!value) {
    return "Unknown time";
  }

  const date = value instanceof Date ? value : new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Unknown time";
  }

  return new Intl.DateTimeFormat(FIXED_LOCALE, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: FIXED_TIME_ZONE,
  }).format(date);
}

export function formatRelativeTime(value: string | Date | null | undefined) {
  if (!value) {
    return "Unknown";
  }

  const date = value instanceof Date ? value : new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }

  const deltaSeconds = Math.round((date.getTime() - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(FIXED_LOCALE, { numeric: "auto" });

  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 60 * 60 * 24 * 365],
    ["month", 60 * 60 * 24 * 30],
    ["week", 60 * 60 * 24 * 7],
    ["day", 60 * 60 * 24],
    ["hour", 60 * 60],
    ["minute", 60],
    ["second", 1],
  ];

  for (const [unit, secondsPerUnit] of units) {
    if (Math.abs(deltaSeconds) >= secondsPerUnit || unit === "second") {
      return formatter.format(Math.round(deltaSeconds / secondsPerUnit), unit);
    }
  }

  return formatter.format(deltaSeconds, "second");
}

export function formatScore(score: number | null | undefined, digits = 0) {
  if (score === null || score === undefined || Number.isNaN(score)) {
    return "N/A";
  }

  return new Intl.NumberFormat(FIXED_LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(score);
}

export function formatScoreDelta(delta: number | null | undefined, digits = 0) {
  if (delta === null || delta === undefined || Number.isNaN(delta)) {
    return "N/A";
  }

  return new Intl.NumberFormat(FIXED_LOCALE, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: "always",
  }).format(delta);
}
