declare module 'electron-log' {
  type LogMethod = (...args: unknown[]) => void;
  const log: {
    error: LogMethod;
    warn: LogMethod;
    info: LogMethod;
    debug: LogMethod;
  };
  export default log;
}
