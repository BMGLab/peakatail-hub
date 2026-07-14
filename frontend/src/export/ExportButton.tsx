import type { RefObject } from 'react'
import './ExportButton.css'

interface ExportButtonProps {
  /** DOM node to export: an <svg>, a <canvas>, or a container with exactly one of either. */
  targetRef: RefObject<HTMLElement | SVGSVGElement | null>
  filename?: string
  /** High-DPI scale factor for PNG export. Default 3x (matches Plotly's toImageButtonOptions). */
  scale?: number
}

function findSvg(node: HTMLElement | SVGSVGElement): SVGSVGElement | null {
  if (node instanceof SVGSVGElement) return node
  return node.querySelector('svg')
}

function findCanvas(node: HTMLElement | SVGSVGElement): HTMLCanvasElement | null {
  if (node instanceof HTMLCanvasElement) return node
  if ('querySelector' in node) return node.querySelector('canvas')
  return null
}

function triggerDownload(href: string, filename: string) {
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
}

async function exportSvg(svg: SVGSVGElement, filename: string) {
  const serializer = new XMLSerializer()
  const source = serializer.serializeToString(svg)
  const blob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  triggerDownload(url, `${filename}.svg`)
  URL.revokeObjectURL(url)
}

async function exportSvgAsPng(svg: SVGSVGElement, filename: string, scale: number) {
  const serializer = new XMLSerializer()
  const source = serializer.serializeToString(svg)
  const svgBlob = new Blob([source], { type: 'image/svg+xml;charset=utf-8' })
  const url = URL.createObjectURL(svgBlob)
  const img = new Image()
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve()
    img.onerror = reject
    img.src = url
  })
  const width = svg.viewBox.baseVal.width || svg.clientWidth || 800
  const height = svg.viewBox.baseVal.height || svg.clientHeight || 600
  const canvas = document.createElement('canvas')
  canvas.width = width * scale
  canvas.height = height * scale
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('canvas 2D context unavailable')
  ctx.scale(scale, scale)
  ctx.drawImage(img, 0, 0, width, height)
  URL.revokeObjectURL(url)
  canvas.toBlob((blob) => {
    if (!blob) return
    const pngUrl = URL.createObjectURL(blob)
    triggerDownload(pngUrl, `${filename}.png`)
    URL.revokeObjectURL(pngUrl)
  }, 'image/png')
}

function exportCanvasAsPng(canvas: HTMLCanvasElement, filename: string) {
  canvas.toBlob((blob) => {
    if (!blob) return
    const url = URL.createObjectURL(blob)
    triggerDownload(url, `${filename}.png`)
    URL.revokeObjectURL(url)
  }, 'image/png')
}

/**
 * Reusable export control: high-DPI PNG + vector SVG. Operates on whatever DOM
 * node is passed in (an <svg>, an element containing one, or a <canvas>).
 * Real geneview export wiring (windowed re-render at export resolution) lands
 * with the GeneviewCanvas renderer; this component is the generic building
 * block both that and the Plotly panels' custom export buttons can reuse.
 */
export function ExportButton({ targetRef, filename = 'peakatail-hub-export', scale = 3 }: ExportButtonProps) {
  function handleSvg() {
    const node = targetRef.current
    if (!node) return
    const svg = findSvg(node)
    if (svg) void exportSvg(svg, filename)
  }

  function handlePng() {
    const node = targetRef.current
    if (!node) return
    const svg = findSvg(node)
    if (svg) {
      void exportSvgAsPng(svg, filename, scale)
      return
    }
    const canvas = findCanvas(node)
    if (canvas) exportCanvasAsPng(canvas, filename)
  }

  return (
    <div className="export-button">
      <button type="button" onClick={handlePng} title="Export high-DPI PNG">
        Export PNG
      </button>
      <button type="button" onClick={handleSvg} title="Export vector SVG">
        Export SVG
      </button>
    </div>
  )
}
