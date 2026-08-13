import { describe, expect, it } from 'vitest'
import { trendDirectionLabel } from './trendDirectionLabel'

describe('trendDirectionLabel', () => {
  it('maps decreasing/increasing to the biological shorten/lengthen wording', () => {
    expect(trendDirectionLabel('decreasing')).toBe("3′UTR shortening")
    expect(trendDirectionLabel('increasing')).toBe("3′UTR lengthening")
  })

  it('falls back to the raw value for anything else, and to a dash for null/undefined', () => {
    expect(trendDirectionLabel('flat')).toBe('flat')
    expect(trendDirectionLabel(null)).toBe('—')
    expect(trendDirectionLabel(undefined)).toBe('—')
  })
})
