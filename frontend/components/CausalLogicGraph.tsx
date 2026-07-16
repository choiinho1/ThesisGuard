import type {
  LogicNodeScore,
  LogicOperator,
  NodeEvidenceVerdict,
  ThesisLogicGraph,
  ThesisLogicNode,
  ThesisScoreBreakdown,
} from "@/types/schema";

const NODE_WIDTH = 226;
const NODE_HEIGHT = 126;
const COLUMN_GAP = 112;
const ROW_GAP = 28;
const CANVAS_PADDING = 36;

const verdictLabel: Record<NodeEvidenceVerdict, string> = {
  SUPPORTED: "기대를 뒷받침",
  REFUTED: "기대와 어긋남",
  CONFLICTING: "근거가 엇갈림",
  INSUFFICIENT: "확인 필요",
};

const operatorLabel: Record<LogicOperator, string> = {
  AND: "모두 필요",
  OR: "하나 이상 필요",
  CONTRIBUTING: "함께 영향을 줌",
};

function finiteNumber(value: number | null | undefined, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function evidenceAxes(score: LogicNodeScore | undefined) {
  const state = finiteNumber(score?.state);
  return {
    support: finiteNumber(score?.support_strength, Math.max(0, state)),
    contradict: finiteNumber(score?.contradict_strength, Math.max(0, -state)),
  };
}

function resolveVerdict(score: LogicNodeScore | undefined): NodeEvidenceVerdict {
  if (score?.verdict && score.verdict in verdictLabel) return score.verdict;
  const axes = evidenceAxes(score);
  if (axes.support > 0 && axes.contradict > 0) return "CONFLICTING";
  if (axes.support > 0) return "SUPPORTED";
  if (axes.contradict > 0) return "REFUTED";
  return "INSUFFICIENT";
}

function verdictClass(verdict: NodeEvidenceVerdict) {
  return `is-${verdict.toLowerCase()}`;
}

interface PositionedNode {
  node: ThesisLogicNode;
  score: LogicNodeScore | undefined;
  verdict: NodeEvidenceVerdict;
  x: number;
  y: number;
}

interface GraphLayout {
  width: number;
  height: number;
  positions: Map<string, PositionedNode>;
}

function layoutGraph(graph: ThesisLogicGraph, scores: Map<string, LogicNodeScore>): GraphLayout {
  const nodesById = new Map(graph.nodes.map((node) => [node.node_id, node]));
  const depths = new Map<string, number>([[graph.root_id, 0]]);

  const walk = (nodeId: string, depth: number, path: Set<string>) => {
    if (path.has(nodeId)) return;
    const node = nodesById.get(nodeId);
    if (!node) return;
    const nextPath = new Set(path).add(nodeId);
    node.child_ids.forEach((childId) => {
      const childDepth = depth + 1;
      if (childDepth > (depths.get(childId) ?? -1)) depths.set(childId, childDepth);
      walk(childId, childDepth, nextPath);
    });
  };
  walk(graph.root_id, 0, new Set());

  let maxDepth = Math.max(0, ...depths.values());
  graph.nodes.forEach((node) => {
    if (!depths.has(node.node_id)) depths.set(node.node_id, maxDepth + 1);
  });
  maxDepth = Math.max(0, ...depths.values());

  const layers = new Map<number, ThesisLogicNode[]>();
  graph.nodes.forEach((node) => {
    const depth = depths.get(node.node_id) ?? maxDepth;
    layers.set(depth, [...(layers.get(depth) ?? []), node]);
  });

  const largestLayer = Math.max(1, ...Array.from(layers.values(), (nodes) => nodes.length));
  const contentWidth =
    CANVAS_PADDING * 2 + (maxDepth + 1) * NODE_WIDTH + maxDepth * COLUMN_GAP;
  const contentHeight =
    CANVAS_PADDING * 2 + largestLayer * NODE_HEIGHT + (largestLayer - 1) * ROW_GAP;
  const width = Math.max(720, contentWidth);
  const height = Math.max(300, contentHeight);
  const horizontalOffset = (width - contentWidth) / 2;
  const positions = new Map<string, PositionedNode>();

  layers.forEach((nodes, depth) => {
    const availableHeight = height - CANVAS_PADDING * 2 - nodes.length * NODE_HEIGHT;
    const gap = nodes.length > 1 ? availableHeight / (nodes.length - 1) : 0;
    const singleNodeY = (height - NODE_HEIGHT) / 2;
    nodes.forEach((node, index) => {
      const x =
        horizontalOffset + CANVAS_PADDING + (maxDepth - depth) * (NODE_WIDTH + COLUMN_GAP);
      const y = nodes.length === 1 ? singleNodeY : CANVAS_PADDING + index * (NODE_HEIGHT + gap);
      const score = scores.get(node.node_id);
      positions.set(node.node_id, {
        node,
        score,
        verdict: resolveVerdict(score),
        x,
        y,
      });
    });
  });

  return { width, height, positions };
}

function edgePath(source: PositionedNode, target: PositionedNode) {
  const sourceX = source.x + NODE_WIDTH;
  const sourceY = source.y + NODE_HEIGHT / 2;
  const targetX = target.x;
  const targetY = target.y + NODE_HEIGHT / 2;
  const bend = Math.max(44, (targetX - sourceX) * 0.45);
  return `M ${sourceX} ${sourceY} C ${sourceX + bend} ${sourceY}, ${targetX - bend} ${targetY}, ${targetX} ${targetY}`;
}

interface CausalLogicGraphProps {
  graph: ThesisLogicGraph;
  scoreBreakdown: ThesisScoreBreakdown;
}

export function CausalLogicGraph({ graph, scoreBreakdown }: CausalLogicGraphProps) {
  const scores = new Map(scoreBreakdown.node_scores.map((score) => [score.node_id, score]));
  const layout = layoutGraph(graph, scores);
  const rootScore = scores.get(graph.root_id);
  const rootVerdict = resolveVerdict(rootScore);
  const edges = graph.nodes.flatMap((target) =>
    target.child_ids.map((childId) => ({ sourceId: childId, targetId: target.node_id })),
  );

  return (
    <section className="score-breakdown-panel" aria-label="투자 논리 인과관계 그래프">
      <div className="score-breakdown-header">
        <div>
          <span>CAUSAL LOGIC GRAPH</span>
          <strong>최종 판단 · {verdictLabel[rootVerdict]}</strong>
        </div>
        <p>
          확인된 범위 <strong>{finiteNumber(scoreBreakdown.coverage_percent).toFixed(1)}%</strong>
        </p>
      </div>

      <div className="causal-graph-legend" aria-hidden="true">
        <span>기대 조건</span>
        <i>→</i>
        <span>중간 결과</span>
        <i>→</i>
        <span>최종 판단</span>
      </div>

      <div className="causal-graph-viewport" tabIndex={0}>
        <svg
          className="causal-graph-canvas"
          preserveAspectRatio="xMidYMid meet"
          role="img"
          style={{ minWidth: `${layout.width}px` }}
          viewBox={`0 0 ${layout.width} ${layout.height}`}
        >
          <title>투자 논리 인과관계</title>
          <desc>왼쪽의 기대 조건이 화살표를 따라 오른쪽의 최종 판단에 어떻게 이어지는지 보여줍니다.</desc>
          <defs>
            <marker
              id="causal-arrow"
              markerHeight="8"
              markerUnits="strokeWidth"
              markerWidth="8"
              orient="auto"
              refX="7"
              refY="4"
              viewBox="0 0 8 8"
            >
              <path className="causal-arrow-head" d="M 0 0 L 8 4 L 0 8 z" />
            </marker>
          </defs>

          <g aria-hidden="true" className="causal-edges">
            {edges.map(({ sourceId, targetId }) => {
              const source = layout.positions.get(sourceId);
              const target = layout.positions.get(targetId);
              if (!source || !target) return null;
              return (
                <path
                  className={`causal-edge ${verdictClass(source.verdict)}`}
                  d={edgePath(source, target)}
                  key={`${sourceId}-${targetId}`}
                  markerEnd="url(#causal-arrow)"
                />
              );
            })}
          </g>

          {Array.from(layout.positions.values(), (position) => {
            const { node, score, verdict, x, y } = position;
            const axes = evidenceAxes(score);
            const isRoot = node.node_id === graph.root_id;
            const role = isRoot ? "최종 판단" : node.kind === "ASSUMPTION" ? "기대 조건" : "중간 결과";
            return (
              <foreignObject height={NODE_HEIGHT} key={node.node_id} width={NODE_WIDTH} x={x} y={y}>
                <article
                  className={`causal-node ${verdictClass(verdict)} ${isRoot ? "is-root" : ""}`}
                >
                  <div className="causal-node-topline">
                    <span>{role}</span>
                    {node.operator && <small>{operatorLabel[node.operator]}</small>}
                    {score?.required && <em>필수</em>}
                  </div>
                  <strong title={node.label}>{node.label}</strong>
                  <div className="causal-node-footer">
                    <span>{verdictLabel[verdict]}</span>
                    <small>긍정 {axes.support.toFixed(2)} · 우려 {axes.contradict.toFixed(2)}</small>
                  </div>
                </article>
              </foreignObject>
            );
          })}
        </svg>
      </div>

      <p className="causal-graph-hint">화살표는 왼쪽 조건이 오른쪽 결과에 영향을 주는 방향을 뜻합니다.</p>

      {scoreBreakdown.is_broken && (
        <div className="score-invalidation-alert" role="alert">
          <strong>기존 판단을 유지하기 어려운 상태</strong>
          {scoreBreakdown.invalidated_assumptions.length > 0 && (
            <p>{scoreBreakdown.invalidated_assumptions.join(" · ")}</p>
          )}
          <span>중요하게 보던 기대와 어긋나는 내용이 연이어 확인됐습니다.</span>
        </div>
      )}
    </section>
  );
}
