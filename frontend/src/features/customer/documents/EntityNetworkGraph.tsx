import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'
import type { EntityNetworkResponse } from '@/types/org'

const Plot = createPlotlyComponent(Plotly)

// Evenly spaced points on a sphere surface — ported from opencrawler's
// Accordion_View._fibonacci_sphere_points so the two apps lay out entity
// nodes the same way (no "focus node" concept here, so no star-layout branch).
function fibonacciSpherePoints(n: number, radius = 2.5): [number, number, number][] {
  const points: [number, number, number][] = []
  if (n <= 0) return points
  const goldenAngle = Math.PI * (3 - Math.sqrt(5))
  for (let i = 0; i < n; i++) {
    const y = n > 1 ? 1 - (i / (n - 1)) * 2 : 0
    const r = Math.sqrt(Math.max(0, 1 - y * y))
    const theta = goldenAngle * i
    points.push([Math.cos(theta) * r * radius, y * radius, Math.sin(theta) * r * radius])
  }
  return points
}

export function EntityNetworkGraph({ network }: { network: EntityNetworkResponse }) {
  const { nodes, edges } = network
  const focus = network.focus_canonical_name ?? null
  if (nodes.length < 2) {
    return <p className="text-sm text-muted">Chưa đủ dữ liệu thực thể để vẽ mạng lưới liên quan.</p>
  }

  const positions = new Map<string, [number, number, number]>()
  if (focus && nodes.some((n) => n.canonical_name === focus)) {
    const others = nodes.filter((n) => n.canonical_name !== focus)
    const weightByOther = new Map(edges.map((e) => [e.target, e.weight]))
    const maxW = Math.max(1, ...others.map((n) => weightByOther.get(n.canonical_name) ?? 0))
    const otherPoints = fibonacciSpherePoints(others.length, 1)
    positions.set(focus, [0, 0, 0])
    others.forEach((n, i) => {
      const w = weightByOther.get(n.canonical_name) ?? 0
      const radius = 3 - 1.8 * (w / maxW)
      const [ux, uy, uz] = otherPoints[i]
      positions.set(n.canonical_name, [ux * radius, uy * radius, uz * radius])
    })
  } else {
    nodes.forEach((n, i) => positions.set(n.canonical_name, fibonacciSpherePoints(nodes.length)[i]))
  }

  const maxWeight = Math.max(1, ...edges.map((e) => e.weight))

  const edgeTraces = edges.map((e) => {
    const [x0, y0, z0] = positions.get(e.source)!
    const [x1, y1, z1] = positions.get(e.target)!
    const xm = (x0 + x1) / 2
    const ym = (y0 + y1) / 2
    const zm = (z0 + z1) / 2
    return {
      type: 'scatter3d',
      mode: 'lines+text',
      x: [x0, xm, x1],
      y: [y0, ym, y1],
      z: [z0, zm, z1],
      line: { width: 1 + 5 * (e.weight / maxWeight), color: '#999999' },
      text: ['', String(e.weight), ''],
      textposition: 'middle center',
      textfont: { size: 12, color: '#c78a1f' },
      hoverinfo: 'text',
      hovertext: focus
        ? `${e.target}: xuất hiện cùng ${focus} trong ${e.weight} bài`
        : `${e.source} ↔ ${e.target}: ${e.weight} bài chung`,
      showlegend: false,
    }
  })

  const nodeTrace = {
    type: 'scatter3d',
    mode: 'markers+text',
    x: nodes.map((n) => positions.get(n.canonical_name)![0]),
    y: nodes.map((n) => positions.get(n.canonical_name)![1]),
    z: nodes.map((n) => positions.get(n.canonical_name)![2]),
    text: nodes.map((n) => n.canonical_name),
    textposition: 'top center',
    marker: {
      size: nodes.map((n) => (n.canonical_name === focus ? 14 : 9)),
      color: nodes.map((n) => (n.canonical_name === focus ? '#fbbf24' : '#8f6110')),
      line: { width: 1, color: '#3a2708' },
    },
    hoverinfo: 'text',
    hovertext: nodes.map((n) => `${n.canonical_name} · xuất hiện trong ${n.post_count} bài`),
    showlegend: false,
  }

  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
        {focus
          ? `Mạng lưới thực thể liên quan — trung tâm: ${focus} (${nodes.length} thực thể, ${edges.length} mối quan hệ)`
          : `Mạng lưới thực thể liên quan (${nodes.length} thực thể, ${edges.length} mối quan hệ)`}
      </p>
      <Plot
        data={[...edgeTraces, nodeTrace]}
        layout={{
          height: 420,
          margin: { l: 0, r: 0, t: 10, b: 0 },
          scene: {
            xaxis: { visible: false },
            yaxis: { visible: false },
            zaxis: { visible: false },
          },
          paper_bgcolor: 'rgba(0,0,0,0)',
        }}
        config={{ displayModeBar: false, responsive: true }}
        style={{ width: '100%' }}
        useResizeHandler
      />
    </div>
  )
}
