<script lang="ts">
	import { scaleLinear } from 'd3-scale';
	import { line as d3Line } from 'd3-shape';
	import { getTranslate } from '@tolgee/svelte';

	const { t } = getTranslate();

	type ComponentId = 'blade' | 'rail' | 'nozzle' | 'cleaning' | 'heater' | 'sensor';

	const COMPONENTS: {
		id: ComponentId;
		label: string;
		color: string;
		mode: 'sawtooth' | 'smooth';
		decay: number;
		maintAt: number;
	}[] = [
		{
			id: 'blade',
			label: 'blade',
			color: '#1f3bd1',
			mode: 'sawtooth',
			decay: 0.018,
			maintAt: 0.18
		},
		{ id: 'rail', label: 'rail', color: '#6cb7f0', mode: 'sawtooth', decay: 0.012, maintAt: 0.2 },
		{
			id: 'nozzle',
			label: 'nozzle',
			color: '#e5333d',
			mode: 'sawtooth',
			decay: 0.06,
			maintAt: 0.15
		},
		{
			id: 'cleaning',
			label: 'cleaning',
			color: '#f4a6a0',
			mode: 'sawtooth',
			decay: 0.024,
			maintAt: 0.18
		},
		{ id: 'heater', label: 'heater', color: '#1e8b72', mode: 'smooth', decay: 0.005, maintAt: 0 },
		{ id: 'sensor', label: 'sensor', color: '#7bd389', mode: 'smooth', decay: 0.0015, maintAt: 0 }
	];

	const HORIZON = 260;
	const EVENT_TICK = 140;
	const EVENT_LABEL = 'human-disruption';

	type Point = { tick: number; health: number };

	// Deterministic pseudo-random so the chart is identical on every render
	function noise(seed: number): number {
		const x = Math.sin(seed * 12.9898) * 43758.5453;
		return x - Math.floor(x);
	}

	function generateSeries(comp: (typeof COMPONENTS)[number]): Point[] {
		const points: Point[] = [];
		let health = 1.0;
		let postEventTau = 14; // exponential decay constant after disruption
		for (let t = 0; t <= HORIZON; t++) {
			if (comp.mode === 'sawtooth') {
				const beforeEvent = t < EVENT_TICK;
				if (beforeEvent) {
					// jitter the decay rate per-tick so lines don't look mechanical
					const jitter = 1 + (noise(t + comp.decay * 1000) - 0.5) * 0.15;
					health -= comp.decay * jitter;
					if (health <= comp.maintAt) {
						// maintenance kick: restore to near 1.0 with small noise
						health = 0.97 + noise(t + comp.label.length) * 0.03;
					}
				} else {
					// post-event: no maintenance, accelerated decay to 0
					const into = t - EVENT_TICK;
					health = Math.max(0, health * Math.exp(-into / postEventTau));
				}
			} else {
				// smooth exponential decay throughout
				health = Math.exp(-t * comp.decay);
			}
			points.push({ tick: t, health: Math.max(0, Math.min(1, health)) });
		}
		return points;
	}

	const series = COMPONENTS.map((c) => ({ ...c, data: generateSeries(c) }));

	// Chart geometry
	const margin = { top: 12, right: 24, bottom: 32, left: 36 };
	const viewW = 1280;
	const viewH = 360;
	const innerW = viewW - margin.left - margin.right;
	const innerH = viewH - margin.top - margin.bottom;

	const xScale = scaleLinear().domain([0, HORIZON]).range([0, innerW]);
	const yScale = scaleLinear().domain([0, 1]).range([innerH, 0]);

	const lineGen = d3Line<Point>()
		.x((d) => xScale(d.tick))
		.y((d) => yScale(d.health));

	const xTicks = [0, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200, 220, 240, 260];
	const yTicks = [0, 0.2, 0.4, 0.6, 0.8, 1.0];

	const eventX = xScale(EVENT_TICK);

	// Health → status mapping (matches the scenario data thresholds)
	function statusOf(health: number): 'FUNCTIONAL' | 'DEGRADED' | 'CRITICAL' | 'FAILED' {
		if (health >= 0.75) return 'FUNCTIONAL';
		if (health >= 0.45) return 'DEGRADED';
		if (health >= 0.2) return 'CRITICAL';
		return 'FAILED';
	}

	// Hover state — null means no tooltip
	type Hover = {
		clientX: number;
		clientY: number;
		tick: number;
		comp: (typeof series)[number];
		health: number;
		status: ReturnType<typeof statusOf>;
	};
	let hover = $state<Hover | null>(null);
	let svgEl = $state<SVGSVGElement | null>(null);

	function handleMove(e: MouseEvent) {
		if (!svgEl) return;
		const rect = svgEl.getBoundingClientRect();
		// Convert client coords → SVG viewBox coords (SVG uses preserveAspectRatio="none")
		const sx = ((e.clientX - rect.left) / rect.width) * viewW - margin.left;
		const sy = ((e.clientY - rect.top) / rect.height) * viewH - margin.top;
		if (sx < 0 || sx > innerW || sy < 0 || sy > innerH) {
			hover = null;
			return;
		}
		const tick = Math.round(xScale.invert(sx));
		// Find series whose health at this tick is closest to the cursor's Y (in data units)
		const cursorHealth = yScale.invert(sy);
		let best: (typeof series)[number] | null = null;
		let bestDiff = Infinity;
		for (const s of series) {
			const point = s.data[tick];
			if (!point) continue;
			const diff = Math.abs(point.health - cursorHealth);
			if (diff < bestDiff) {
				bestDiff = diff;
				best = s;
			}
		}
		const bestPoint = best?.data[tick];
		if (!best || !bestPoint) {
			hover = null;
			return;
		}
		hover = {
			clientX: e.clientX - rect.left,
			clientY: e.clientY - rect.top,
			tick,
			comp: best,
			health: bestPoint.health,
			status: statusOf(bestPoint.health)
		};
	}

	function handleLeave() {
		hover = null;
	}

	// Convert hover tick + health back to client (wrapper-relative) px for the focal dot
	const hoverDotX = $derived(
		hover && svgEl
			? ((margin.left + xScale(hover.tick)) / viewW) * svgEl.getBoundingClientRect().width
			: 0
	);
	const hoverDotY = $derived(
		hover && svgEl
			? ((margin.top + yScale(hover.health)) / viewH) * svgEl.getBoundingClientRect().height
			: 0
	);
</script>

<section class="health-timeline">
	<header class="ht-head">
		<div class="ht-eyebrow">Phase 1 / Coupled engine</div>
		<h2 class="ht-title">Component health over time</h2>
	</header>

	<div class="ht-legend">
		{#each COMPONENTS as comp (comp.id)}
			<span class="ht-legend-item">
				<span class="ht-legend-dot" style:--c={comp.color}></span>
				<span class="ht-legend-label">{comp.label}</span>
			</span>
		{/each}
	</div>

	<div class="ht-chart-wrap">
		<svg
			bind:this={svgEl}
			class="ht-chart"
			viewBox={`0 0 ${viewW} ${viewH}`}
			preserveAspectRatio="none"
			role="img"
			aria-label={$t('a11y.copilot_health_chart')}
			onmousemove={handleMove}
			onmouseleave={handleLeave}
		>
			<g transform={`translate(${margin.left}, ${margin.top})`}>
				<!-- Y gridlines + labels -->
				{#each yTicks as v (v)}
					<line class="ht-grid" x1="0" x2={innerW} y1={yScale(v)} y2={yScale(v)} />
					<text
						class="ht-axis-label"
						x="-8"
						y={yScale(v)}
						text-anchor="end"
						dominant-baseline="middle"
					>
						{v.toFixed(1)}
					</text>
				{/each}

				<!-- X gridlines + labels -->
				{#each xTicks as t (t)}
					<line class="ht-grid ht-grid-x" x1={xScale(t)} x2={xScale(t)} y1="0" y2={innerH} />
					<text class="ht-axis-label" x={xScale(t)} y={innerH + 18} text-anchor="middle">
						{t}
					</text>
				{/each}

				<!-- Event marker -->
				<line class="ht-event-line" x1={eventX} x2={eventX} y1="0" y2={innerH} />
				<text class="ht-event-label" x={eventX + 6} y="14">{EVENT_LABEL}</text>

				<!-- Series -->
				{#each series as s (s.id)}
					<path class="ht-line" d={lineGen(s.data) ?? ''} stroke={s.color} />
				{/each}

				<!-- Hover guideline -->
				{#if hover}
					<line
						class="ht-hover-line"
						x1={xScale(hover.tick)}
						x2={xScale(hover.tick)}
						y1="0"
						y2={innerH}
					/>
				{/if}

				<!-- X axis tick text label -->
				<text class="ht-axis-title" x={innerW / 2} y={innerH + 32} text-anchor="middle">
					tick
				</text>

				<!-- Transparent capture rect — covers the inner chart area for mouse tracking -->
				<rect class="ht-capture" x="0" y="0" width={innerW} height={innerH} />
			</g>
		</svg>

		{#if hover}
			<span
				class="ht-focus-dot"
				style:--c={hover.comp.color}
				style:left="{hoverDotX}px"
				style:top="{hoverDotY}px"
			></span>
			<div
				class="ht-tooltip"
				style:left="{Math.min(
					hover.clientX + 14,
					(svgEl?.getBoundingClientRect().width ?? 0) - 220
				)}px"
				style:top="{Math.max(hover.clientY - 10, 0)}px"
			>
				<div class="ht-tip-row">
					<span class="ht-tip-key">component_id</span>
					<span class="ht-tip-val">{hover.comp.id}</span>
				</div>
				<div class="ht-tip-row">
					<span class="ht-tip-key">tick</span>
					<span class="ht-tip-val">{hover.tick}</span>
				</div>
				<div class="ht-tip-row">
					<span class="ht-tip-key">health</span>
					<span class="ht-tip-val">{hover.health.toFixed(3)}</span>
				</div>
				<div class="ht-tip-row">
					<span class="ht-tip-key">status</span>
					<span class="ht-tip-val">{hover.status}</span>
				</div>
			</div>
		{/if}
	</div>

	<p class="ht-foot">
		Grey dashed rules mark environmental events from the scenario (chaos overlays — earthquake, HVAC
		failure, holiday, …).
	</p>
</section>

<style>
	.health-timeline {
		--accent: #024ad8;
		--fg: #000000;
		--fg-3: #5a5a5a;
		--fg-4: #8a8a8a;
		--line: #e6e6e6;
		--sans: 'Wix Madefor Text', 'HP Simplified', 'Helvetica Neue', Helvetica, Arial, sans-serif;
		--display:
			'Wix Madefor Display', 'HP Simplified', 'Helvetica Neue', Helvetica, Arial, sans-serif;

		max-width: 1280px;
		margin: 0 auto;
		padding: 32px 40px 56px;
		font-family: var(--sans);
		color: var(--fg);
	}

	.ht-head {
		margin-bottom: 18px;
	}
	.ht-eyebrow {
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.16em;
		color: var(--accent);
		text-transform: uppercase;
		margin-bottom: 6px;
	}
	.ht-title {
		font-family: var(--display);
		font-size: clamp(22px, 2.4vw, 30px);
		font-weight: 800;
		letter-spacing: -0.025em;
		margin: 0;
		color: var(--fg);
	}

	.ht-legend {
		display: flex;
		flex-wrap: wrap;
		gap: 18px;
		margin: 14px 0 12px;
	}
	.ht-legend-item {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		font-size: 13px;
		color: var(--fg);
	}
	.ht-legend-dot {
		width: 12px;
		height: 12px;
		border-radius: 50%;
		background: white;
		border: 2.5px solid var(--c);
		flex-shrink: 0;
	}
	.ht-legend-label {
		font-weight: 500;
	}

	.ht-chart-wrap {
		position: relative;
		width: 100%;
	}
	.ht-chart {
		width: 100%;
		height: auto;
		display: block;
	}
	.ht-capture {
		fill: transparent;
		pointer-events: all;
		cursor: crosshair;
	}
	.ht-hover-line {
		stroke: #1a1a1a;
		stroke-width: 1;
		stroke-dasharray: 2 3;
		opacity: 0.5;
		pointer-events: none;
	}
	.ht-focus-dot {
		position: absolute;
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: white;
		border: 2px solid var(--c);
		transform: translate(-50%, -50%);
		pointer-events: none;
		box-shadow: 0 0 0 3px rgba(2, 74, 216, 0.08);
	}
	.ht-tooltip {
		position: absolute;
		min-width: 200px;
		padding: 10px 14px;
		background: #ffffff;
		border: 1px solid #d4d4d4;
		border-radius: 8px;
		box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
		font-family: var(--sans);
		font-size: 12.5px;
		pointer-events: none;
		z-index: 10;
	}
	.ht-tip-row {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 18px;
		padding: 3px 0;
	}
	.ht-tip-key {
		color: var(--fg-3);
		font-weight: 400;
	}
	.ht-tip-val {
		color: var(--fg);
		font-weight: 700;
		font-feature-settings:
			'tnum' 1,
			'zero' 1;
	}

	.ht-grid {
		stroke: var(--line);
		stroke-width: 1;
	}
	.ht-grid-x {
		stroke: #f0f0f0;
	}
	.ht-axis-label {
		font-size: 11px;
		fill: var(--fg-4);
		font-family: var(--sans);
	}
	.ht-axis-title {
		font-size: 11px;
		fill: var(--fg-3);
		font-family: var(--sans);
	}
	.ht-line {
		fill: none;
		stroke-width: 1.6;
		stroke-linejoin: round;
		stroke-linecap: round;
	}
	.ht-event-line {
		stroke: #888;
		stroke-width: 1;
		stroke-dasharray: 4 4;
	}
	.ht-event-label {
		font-size: 11px;
		font-weight: 600;
		fill: var(--fg-3);
		font-family: var(--sans);
	}

	.ht-foot {
		margin: 18px 0 0;
		font-size: 13px;
		color: var(--fg-3);
		line-height: 1.5;
	}
</style>
