import { cache } from 'react';
import { getDoc, getRun } from './storage';

/** Request-scoped memoisation so a layout and its page share one blob read. */
export const loadRun = cache(getRun);
export const loadDoc = cache(getDoc);
