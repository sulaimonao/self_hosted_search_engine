import type { Logger } from 'winston';
import type { Format } from 'logform';

declare const logger: Logger;

export default logger;

export declare function createComponentLogger(component: string, meta?: Record<string, unknown>): Logger;
export declare function withCorrelationId(baseLogger: Logger, correlationId?: string | null | undefined): Logger;
export declare function getLogDirectory(): string;
export declare const combineMessageAndSplat: Format;
