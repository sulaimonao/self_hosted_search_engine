const fs = require('node:fs');
const path = require('node:path');
const util = require('node:util');
const { createLogger, format, transports } = require('winston');
const DailyRotateFile = require('winston-daily-rotate-file');

const SPLAT = Symbol.for('splat');
const MESSAGE = Symbol.for('message');

const ENV_NAME = (process.env.NODE_ENV || '').toLowerCase();
const IS_DEV = ENV_NAME === '' || ENV_NAME === 'development' || ENV_NAME === 'dev';
const DEFAULT_LOG_LEVEL = (process.env.LOG_LEVEL || (IS_DEV ? 'debug' : 'info')).toLowerCase();
const DEFAULT_COMPONENT = process.env.LOG_COMPONENT || 'node';
const MAX_JSONL_MESSAGE_LENGTH = Number.parseInt(process.env.LOG_MAX_MESSAGE_LENGTH || '2000', 10);
const MAX_JSONL_STACK_LENGTH = Number.parseInt(process.env.LOG_MAX_STACK_LENGTH || '8000', 10);

function truncateString(value, limit) {
  if (typeof value !== 'string') {
    return value;
  }
  if (!Number.isFinite(limit) || limit <= 0 || value.length <= limit) {
    return value;
  }
  const truncated = value.slice(0, limit);
  return `${truncated}…[truncated ${value.length - limit} chars]`;
}

function ensureDir(dirPath) {
  if (!dirPath) {
    return;
  }
  try {
    fs.mkdirSync(dirPath, { recursive: true });
  } catch (error) {
    // eslint-disable-next-line no-console
    console.warn('[logger] failed to ensure log dir', { dirPath, error });
  }
}

function resolveElectronLogDir() {
  if (!process.versions || !process.versions.electron) {
    return null;
  }
  try {
    // Lazy require so non-Electron contexts don't attempt to load the module
    // eslint-disable-next-line global-require, import/no-extraneous-dependencies
    const { app } = require('electron');
    if (app && typeof app.getPath === 'function') {
      return path.join(app.getPath('userData'), 'logs');
    }
  } catch (error) {
    // eslint-disable-next-line no-console
    console.warn('[logger] unable to resolve electron log dir', error);
  }
  return null;
}

function resolveEventName(info) {
  const candidate = info.event || info.eventName || info.meta?.event;
  if (typeof candidate === 'string' && candidate.trim().length > 0) {
    return candidate.trim();
  }
  return 'log';
}

const RESOLVED_LOG_DIR = (() => {
  const override = process.env.LOG_DIR && process.env.LOG_DIR.trim();
  if (override) {
    const resolved = path.resolve(override);
    ensureDir(resolved);
    return resolved;
  }
  const electronDir = resolveElectronLogDir();
  if (electronDir) {
    ensureDir(electronDir);
    return electronDir;
  }
  const fallback = path.resolve(process.cwd(), 'logs');
  ensureDir(fallback);
  return fallback;
})();

function extractCorrelationId(info) {
  return (
    info.correlationId ||
    info.correlation_id ||
    info.correlationID ||
    info.correlation ||
    info.cid ||
    (info.meta && info.meta.correlationId) ||
    null
  );
}

function stripInternals(info) {
  const meta = {};
  const skip = new Set([
    'level',
    'message',
    'timestamp',
    'stack',
    'component',
    'event',
    'eventName',
    'correlationId',
    'correlation_id',
    'correlationID',
    'correlation',
    'cid',
  ]);
  for (const key of Object.keys(info)) {
    if (skip.has(key)) continue;
    meta[key] = info[key];
  }
  const splat = info[SPLAT];
  if (Array.isArray(splat) && splat.length) {
    meta.splat = splat;
  }
  const messageSymbol = info[MESSAGE];
  if (messageSymbol) {
    meta.rawMessage = messageSymbol;
  }
  return meta;
}

function safeMeta(info) {
  const meta = stripInternals(info);
  if (!meta || Object.keys(meta).length === 0) {
    return undefined;
  }
  return meta;
}

const combineMessageAndSplat = format((info) => {
  const splat = info[SPLAT];
  if (!splat || splat.length === 0) {
    return info;
  }
  info.message = util.format(info.message, ...splat);
  return info;
});

const baseFormat = format.combine(
  combineMessageAndSplat(),
  format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
  format.errors({ stack: true }),
);

function textLineFormatter(info) {
  const correlationId = extractCorrelationId(info);
  const component = info.component || 'node';
  const level = String(info.level || 'info').toUpperCase();
  const eventName = resolveEventName(info);
  const parts = [info.timestamp, `[${level}]`, `(${component})`];
  if (correlationId) {
    parts.push(`cid=${correlationId}`);
  }
  if (eventName) {
    parts.push(`evt=${eventName}`);
  }
  const meta = safeMeta(info);
  const rawMessage = info.stack || info.message || '';
  const message = truncateString(rawMessage, MAX_JSONL_MESSAGE_LENGTH);
  if (meta) {
    return `${parts.join(' ')} ${message} ${JSON.stringify(meta)}`.trim();
  }
  return `${parts.join(' ')} ${message}`.trim();
}

function jsonLineFormatter(info) {
  const meta = safeMeta(info);
  const eventName = resolveEventName(info);
  const payload = {
    timestamp: info.timestamp,
    level: String(info.level || 'info').toLowerCase(),
    component: info.component || 'node',
    correlation_id: extractCorrelationId(info),
    event: eventName,
    message: truncateString(info.message, MAX_JSONL_MESSAGE_LENGTH),
  };
  if (info.stack) {
    payload.stack = truncateString(info.stack, MAX_JSONL_STACK_LENGTH);
  }
  if (meta) {
    payload.meta = meta;
  }
  return JSON.stringify(payload);
}

const dailyRotateConfig = {
  dirname: RESOLVED_LOG_DIR,
  datePattern: 'YYYY-MM-DD',
  maxSize: '5m',
  maxFiles: '14d',
  zippedArchive: false,
};

const transportList = [
  new transports.File({
    filename: path.join(RESOLVED_LOG_DIR, 'app.log'),
    maxsize: 10 * 1024 * 1024,
    maxFiles: 5,
    tailable: true,
    format: format.combine(baseFormat, format.printf(textLineFormatter)),
  }),
  new DailyRotateFile({
    ...dailyRotateConfig,
    filename: 'app-%DATE%.log',
    format: format.combine(baseFormat, format.printf(textLineFormatter)),
  }),
  new DailyRotateFile({
    ...dailyRotateConfig,
    filename: 'app-%DATE%.jsonl',
    format: format.combine(baseFormat, format.printf(jsonLineFormatter)),
  }),
];

if (process.env.NODE_ENV !== 'production') {
  transportList.push(
    new transports.Console({
      handleExceptions: true,
      handleRejections: true,
      format: format.combine(
        format.colorize({ all: true }),
        baseFormat,
        format.printf((info) => {
          const meta = safeMeta(info);
          const correlationId = extractCorrelationId(info);
          const component = info.component || 'node';
          const eventName = resolveEventName(info);
          const prefix = correlationId
            ? `[${info.level}] (${component}) cid=${correlationId}`
            : `[${info.level}] (${component})`;
          const suffixParts = [];
          if (eventName) {
            suffixParts.push(`evt=${eventName}`);
          }
          const renderedMessage = truncateString(info.stack || info.message, MAX_JSONL_MESSAGE_LENGTH);
          suffixParts.push(renderedMessage);
          if (meta) {
            suffixParts.push(JSON.stringify(meta));
          }
          return `${prefix} ${suffixParts.join(' ')}`;
        }),
      ),
    }),
  );
}

const logger = createLogger({
  level: DEFAULT_LOG_LEVEL,
  defaultMeta: { component: DEFAULT_COMPONENT },
  transports: transportList,
  exitOnError: false,
});

function createComponentLogger(component, meta = {}) {
  return logger.child({ component, ...meta });
}

function withCorrelationId(baseLogger, correlationId) {
  if (!correlationId) {
    return baseLogger;
  }
  return baseLogger.child({ correlationId });
}

module.exports = logger;
module.exports.createComponentLogger = createComponentLogger;
module.exports.withCorrelationId = withCorrelationId;
module.exports.getLogDirectory = () => RESOLVED_LOG_DIR;
module.exports.combineMessageAndSplat = combineMessageAndSplat;
module.exports.truncateString = truncateString;
