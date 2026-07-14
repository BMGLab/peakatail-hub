// plotly.js-dist-min ships no type declarations of its own; it is a prebuilt
// bundle of the same public API as `plotly.js` (just without the geo/mapbox
// traces to keep bundle size down), so we alias it to @types/plotly.js.
declare module 'plotly.js-dist-min' {
  import * as Plotly from 'plotly.js'
  export = Plotly
}
