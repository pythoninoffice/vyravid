/**
 * Custom logger that automatically disables console logs in production
 *
 * Usage:
 *   import { logger } from '@/utils/logger'
 *
 *   logger.log('Debug info')
 *   logger.warn('Warning message')
 *   logger.error('Error occurred')
 */

const isDevelopment = import.meta.env.DEV

export const logger = {
  log: (...args: any[]) => {
    if (isDevelopment) {
      console.log(...args)
    }
  },

  warn: (...args: any[]) => {
    if (isDevelopment) {
      console.warn(...args)
    }
  },

  error: (...args: any[]) => {
    // Keep errors in production for debugging critical issues
    console.error(...args)
  },

  info: (...args: any[]) => {
    if (isDevelopment) {
      console.info(...args)
    }
  },

  debug: (...args: any[]) => {
    if (isDevelopment) {
      console.debug(...args)
    }
  },

  table: (...args: any[]) => {
    if (isDevelopment) {
      console.table(...args)
    }
  },

  group: (label?: string) => {
    if (isDevelopment) {
      console.group(label)
    }
  },

  groupEnd: () => {
    if (isDevelopment) {
      console.groupEnd()
    }
  }
}

// Optional: Override global console in production to catch accidental console.log()
if (!isDevelopment) {
  const noop = () => {}

  // Override console methods in production (except error)
  console.log = noop
  console.warn = noop
  console.info = noop
  console.debug = noop
  console.table = noop
}
