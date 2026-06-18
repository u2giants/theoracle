export const ORACLE_TIME_ZONE = 'America/New_York';

type DateLike = Date | string | number;

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  timeZone: ORACLE_TIME_ZONE,
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
});

const DATE_FORMATTER = new Intl.DateTimeFormat('en-US', {
  timeZone: ORACLE_TIME_ZONE,
  month: 'short',
  day: 'numeric',
  year: 'numeric',
});

const TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  timeZone: ORACLE_TIME_ZONE,
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
});

function toDate(value: DateLike): Date {
  return value instanceof Date ? value : new Date(value);
}

export function formatNYDateTime(value: DateLike): string {
  return DATE_TIME_FORMATTER.format(toDate(value));
}

export function formatNYDate(value: DateLike): string {
  return DATE_FORMATTER.format(toDate(value));
}

export function formatNYTime(value: DateLike): string {
  return TIME_FORMATTER.format(toDate(value));
}
