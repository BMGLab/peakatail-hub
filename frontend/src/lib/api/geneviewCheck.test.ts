import { describe, expect, it } from 'vitest'
import { parseGeneviewCheckResponse } from './client'

// checkGeneviewRender itself short-circuits to {ok: true} under USE_MOCKS
// (this repo's tests run mocks-on by default -- see client.ts's doc
// comment), so the real Response-parsing logic is tested directly here
// against constructed Response objects instead.
describe('parseGeneviewCheckResponse', () => {
  it('resolves ok:true for a 200 response', async () => {
    const res = new Response('<html>...</html>', { status: 200 })
    await expect(parseGeneviewCheckResponse(res)).resolves.toEqual({ ok: true })
  })

  it('surfaces the renderer\'s real "no PAS expressed" 404 message body as ok:false', async () => {
    const message =
      'gene ENSG00000000000 has no PAS expressed in cell type CELL_TYPES_WANSLEEBEN_HOGAN_2013_ENDOTHELIAL — no APA data to plot here.'
    const res = new Response(message, { status: 404 })
    await expect(parseGeneviewCheckResponse(res)).resolves.toEqual({ ok: false, status: 404, message })
  })

  it('falls back to a generic message when the error body is empty', async () => {
    const res = new Response('', { status: 500 })
    await expect(parseGeneviewCheckResponse(res)).resolves.toEqual({
      ok: false,
      status: 500,
      message: 'Failed to generate geneview (HTTP 500).',
    })
  })
})
