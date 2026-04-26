<script lang="ts">
	import { getTranslate } from '@tolgee/svelte';
	import { scaleLinear } from 'd3-scale';
	import { line as d3Line } from 'd3-shape';
	import { useQuery } from 'convex-svelte';
	import { useTimeWindow } from '$lib/dashboard/time-window.svelte';
	import { api } from '$lib/convex/_generated/api';
	import type { Id } from '$lib/convex/_generated/dataModel';

	const { t } = getTranslate();

	const { runId = null }: { runId?: Id<'simRuns'> | null } = $props();

	// ──────────────────────────────────────────────────────────────────────
	// SHARED — palette, constants
	// ──────────────────────────────────────────────────────────────────────
	const STATUS_COLORS = {
		FUNCTIONAL: '#ECECEC',
		DEGRADED: '#6B7FE5',
		CRITICAL: '#024AD8',
		FAILED: '#0A0A0A'
	} as const;
	type Status = keyof typeof STATUS_COLORS;

	const HORIZON = 260; // tick count — matches health-timeline so the shared TimeWindow aligns
	const NOW_TICK = 200; // operational load goes flat after this tick

	// Deterministic pseudo-random
	function noise(seed: number): number {
		const x = Math.sin(seed * 12.9898) * 43758.5453;
		return x - Math.floor(x);
	}

	// ──────────────────────────────────────────────────────────────────────
	// PANEL TOP — Driver streams (4 sparklines)
	// ──────────────────────────────────────────────────────────────────────
	type Driver = {
		id: 'temperature_stress' | 'humidity_contamination' | 'operational_load' | 'maintenance_level';
		labelKey: string;
		flatten: boolean; // simulates "load shedding" — flat after NOW
	};
	const DRIVERS: Driver[] = [
		{ id: 'temperature_stress', labelKey: 'sim_ui.drivers.temperature_stress', flatten: false },
		{
			id: 'humidity_contamination',
			labelKey: 'sim_ui.drivers.humidity_contamination',
			flatten: false
		},
		{ id: 'operational_load', labelKey: 'sim_ui.drivers.operational_load', flatten: true },
		{ id: 'maintenance_level', labelKey: 'sim_ui.drivers.maintenance_level', flatten: true }
	];

	type Point = { tick: number; v: number };

	function genDriver(d: Driver): Point[] {
		const out: Point[] = [];
		// Each driver gets a unique waveform via different freq/phase/baseline.
		const seed = d.id.charCodeAt(0) + d.id.charCodeAt(d.id.length - 1);
		const baseline =
			d.id === 'temperature_stress'
				? 0.45
				: d.id === 'humidity_contamination'
					? 0.35
					: d.id === 'operational_load'
						? 0.5
						: 0.7;
		const freq = d.id === 'maintenance_level' ? 0 : 0.08 + (seed % 5) * 0.012;
		const amp = d.id === 'maintenance_level' ? 0 : 0.14 + (seed % 4) * 0.02;

		for (let t = 0; t <= HORIZON; t++) {
			let v: number;
			if (d.flatten && t > NOW_TICK) {
				// Hold last value flat (load shedding visual)
				v = out[NOW_TICK]?.v ?? baseline;
			} else if (d.id === 'maintenance_level') {
				v = baseline; // perfectly flat
			} else {
				const wave = Math.sin(t * freq + seed) * amp;
				const sub = Math.sin(t * freq * 2.7 + seed * 0.3) * amp * 0.35;
				const jitter = (noise(t * 7 + seed) - 0.5) * 0.06;
				v = baseline + wave + sub + jitter;
			}
			out.push({ tick: t, v: Math.max(0, Math.min(1, v)) });
		}
		return out;
	}

	const syntheticDriverData = DRIVERS.map((d) => ({ ...d, data: genDriver(d) }));

	// Real driver streams from the historian. One query, returns 4 series in
	// a single payload — cheaper than 4 separate queries per component.
	const driversTSQuery = useQuery(api.sim.queries.getDriversTimeseries, () =>
		runId ? { runId } : 'skip'
	);
	const realDriverData = $derived.by(() => {
		const rows = driversTSQuery.data;
		if (!runId || !rows || rows.length === 0) return null;
		const map: Record<Driver['id'], Point[]> = {
			temperature_stress: rows.map((r) => ({ tick: r.tick, v: r.temperatureStress })),
			humidity_contamination: rows.map((r) => ({ tick: r.tick, v: r.humidityContamination })),
			operational_load: rows.map((r) => ({ tick: r.tick, v: r.operationalLoad })),
			maintenance_level: rows.map((r) => ({ tick: r.tick, v: r.maintenanceLevel }))
		};
		return DRIVERS.map((d) => ({ ...d, data: map[d.id] }));
	});

	const driverData = $derived(realDriverData ?? syntheticDriverData);

	// ──────────────────────────────────────────────────────────────────────
	// Phase 2 time-window — provided by the dashboard so the same selector
	// drives Component health over time AND the driver/alerts block.
	// Falls back to a local instance when this block is rendered standalone.
	// Mirrors the Streamlit panel-1 control (sim/.../streamlit_app.py:386-418).
	// ──────────────────────────────────────────────────────────────────────
	const tw = useTimeWindow(HORIZON);

	const startTick = $derived(tw.startTick);
	const endTick = $derived(tw.endTick);
	const windowLabel = $derived(tw.windowLabel);

	// Filter driver and alerts data to the selected window.
	const visibleDriverData = $derived(
		driverData.map((d) => ({
			...d,
			data: d.data.filter((p) => p.tick >= startTick && p.tick < endTick)
		}))
	);

	// Sparkline geometry (per strip) — compact so two columns fit side-by-side
	const sparkW = 600;
	const sparkH = 40;
	const sparkPadX = 8;
	const sparkPadY = 6;
	const sparkInnerW = sparkW - sparkPadX * 2;
	const sparkInnerH = sparkH - sparkPadY * 2;

	const xSpark = $derived(
		scaleLinear()
			.domain([startTick, Math.max(startTick + 1, endTick - 1)])
			.range([0, sparkInnerW])
	);
	const ySpark = scaleLinear().domain([0, 1]).range([sparkInnerH, 0]);
	const sparkLine = $derived(
		d3Line<Point>()
			.x((d) => xSpark(d.tick))
			.y((d) => ySpark(d.v))
	);

	type SparkHover = {
		driverId: Driver['id'];
		clientX: number;
		clientY: number;
		tick: number;
		v: number;
	};
	let sparkHover = $state<SparkHover | null>(null);
	let sparkRefs = $state<Record<string, SVGSVGElement | null>>({});

	function handleSparkMove(e: MouseEvent, d: (typeof driverData)[number]) {
		const svg = sparkRefs[d.id];
		if (!svg) return;
		const rect = svg.getBoundingClientRect();
		const sx = ((e.clientX - rect.left) / rect.width) * sparkW - sparkPadX;
		if (sx < 0 || sx > sparkInnerW) {
			sparkHover = null;
			return;
		}
		// Invert with the windowed scale, then clamp to the visible range.
		const raw = Math.round(xSpark.invert(sx));
		const tick = Math.max(startTick, Math.min(endTick - 1, raw));
		const point = d.data[tick];
		if (!point) {
			sparkHover = null;
			return;
		}
		sparkHover = {
			driverId: d.id,
			clientX: e.clientX - rect.left,
			clientY: e.clientY - rect.top,
			tick,
			v: point.v
		};
	}
	function handleSparkLeave() {
		sparkHover = null;
	}

	function fmtPct(v: number): string {
		return `${Math.round(v * 100)}%`;
	}

	// ──────────────────────────────────────────────────────────────────────
	// SIDE PANEL — Proactive alerts feed (Phase 3 / Autonomy preview)
	// Placeholder data; will be derived from the active simulation run.
	// ──────────────────────────────────────────────────────────────────────
	type AlertSeverity = 'CRITICAL' | 'FAILED' | 'DEGRADED';
	type ComponentId = 'blade' | 'rail' | 'nozzle' | 'cleaning' | 'heater' | 'sensor';
	type ProactiveAlert = {
		tick: number;
		component: ComponentId;
		status: AlertSeverity;
		topDriverKey: string;
		topDriverValue: number;
	};

	const PROACTIVE_ALERTS: ProactiveAlert[] = [
		{
			tick: 31,
			component: 'heater',
			status: 'CRITICAL',
			topDriverKey: 'cleaning_efficiency',
			topDriverValue: 0.834
		},
		{
			tick: 38,
			component: 'rail',
			status: 'CRITICAL',
			topDriverKey: 'powder_spread_quality',
			topDriverValue: 0.705
		},
		{
			tick: 39,
			component: 'blade',
			status: 'CRITICAL',
			topDriverKey: 'powder_spread_quality',
			topDriverValue: 0.689
		},
		{
			tick: 43,
			component: 'cleaning',
			status: 'CRITICAL',
			topDriverKey: 'powder_spread_quality',
			topDriverValue: 0.848
		},
		{
			tick: 58,
			component: 'blade',
			status: 'FAILED',
			topDriverKey: 'cleaning_efficiency',
			topDriverValue: 0.853
		},
		{
			tick: 58,
			component: 'rail',
			status: 'FAILED',
			topDriverKey: 'cleaning_efficiency',
			topDriverValue: 0.853
		},
		{
			tick: 62,
			component: 'heater',
			status: 'FAILED',
			topDriverKey: 'powder_spread_quality',
			topDriverValue: 0.948
		},
		{
			tick: 109,
			component: 'cleaning',
			status: 'FAILED',
			topDriverKey: 'powder_spread_quality',
			topDriverValue: 0.782
		},
		{
			tick: 224,
			component: 'sensor',
			status: 'DEGRADED',
			topDriverKey: 'blade_loss_frac',
			topDriverValue: 1.0
		}
	];

	// Distinct palette for the alerts feed — independent of the heatmap's
	// STATUS_COLORS so the right column reads as a notification log
	// (amber = caution, mid-blue = critical, electric blue = failed) rather
	// than as another swatch from the degradation grid.
	const SEVERITY_COLOR: Record<AlertSeverity, string> = {
		DEGRADED: '#E8A93B',
		CRITICAL: '#5683FF',
		FAILED: '#1846F5'
	};

	function fmtDriverValue(v: number): string {
		return v.toFixed(3);
	}

	// Real status transitions from the historian. The Convex query also joins
	// in the dominant coupling factor at each transition tick so the alert
	// row can show "top driver = X" without a second round-trip.
	const transitionsQuery = useQuery(api.sim.queries.getStatusTransitionsWithDrivers, () =>
		runId ? { runId } : 'skip'
	);
	const realAlerts = $derived.by((): ProactiveAlert[] | null => {
		const rows = transitionsQuery.data;
		if (!runId || !rows || rows.length === 0) return null;
		// Show only DEGRADED / CRITICAL / FAILED — every component starts FUNCTIONAL.
		const allowed = new Set<AlertSeverity>(['DEGRADED', 'CRITICAL', 'FAILED']);
		return rows
			.filter((r) => allowed.has(r.status as AlertSeverity))
			.map((r) => ({
				tick: r.firstTick,
				component: r.componentId as ComponentId,
				status: r.status as AlertSeverity,
				topDriverKey: r.topDriverKey ?? '—',
				topDriverValue: r.topDriverValue ?? 0
			}));
	});
	const alertsList = $derived(realAlerts ?? PROACTIVE_ALERTS);
	const visibleAlerts = $derived(alertsList.filter((a) => a.tick >= startTick && a.tick < endTick));

	// ──────────────────────────────────────────────────────────────────────
	// PANEL BOTTOM — Component degradation grid
	// ──────────────────────────────────────────────────────────────────────
	type ComponentRow = {
		id: string;
		label: string;
		code: string;
		subsystem: string;
		// transitions: bucket index where status changes
		degAt: number;
		critAt: number;
		failAt: number;
	};

	const BUCKETS = 64;
	const NOW_BUCKET = 32; // halfway

	const COMPONENT_ROWS: ComponentRow[] = [
		// nozzle fails earliest, blade & heater fail near NOW, rail late, cleaning late-ish, sensor stays functional
		{
			id: 'blade',
			label: 'Recoater Blade',
			code: 'RB-001',
			subsystem: 'SS-01',
			degAt: 22,
			critAt: 28,
			failAt: 34
		},
		{
			id: 'rail',
			label: 'Linear Rail',
			code: 'LR-002',
			subsystem: 'SS-01',
			degAt: 48,
			critAt: 60,
			failAt: 999
		},
		{
			id: 'nozzle',
			label: 'Nozzle Plate',
			code: 'NP-003',
			subsystem: 'SS-02',
			degAt: 6,
			critAt: 11,
			failAt: 18
		},
		{
			id: 'cleaning',
			label: 'Cleaning Interface',
			code: 'CI-004',
			subsystem: 'SS-02',
			degAt: 26,
			critAt: 36,
			failAt: 46
		},
		{
			id: 'heater',
			label: 'Heating Elements',
			code: 'HE-005',
			subsystem: 'SS-03',
			degAt: 20,
			critAt: 28,
			failAt: 34
		},
		{
			id: 'sensor',
			label: 'Temp Sensor',
			code: 'TS-006',
			subsystem: 'SS-03',
			degAt: 999,
			critAt: 999,
			failAt: 999
		}
	];

	function statusAt(row: ComponentRow, bucket: number): Status {
		if (bucket >= row.failAt) return 'FAILED';
		if (bucket >= row.critAt) return 'CRITICAL';
		if (bucket >= row.degAt) return 'DEGRADED';
		return 'FUNCTIONAL';
	}

	const syntheticComponentMatrix = COMPONENT_ROWS.map((row) => ({
		...row,
		cells: Array.from({ length: BUCKETS }, (_, b) => statusAt(row, b))
	}));

	// Real component-state per row, downsampled to BUCKETS columns by the
	// "worst status in the bucket" rule (FAILED > CRITICAL > DEGRADED > FUNCTIONAL)
	// so a single FAILED tick in a bucket window paints the cell black.
	const STATUS_RANK: Record<Status, number> = {
		FUNCTIONAL: 0,
		DEGRADED: 1,
		CRITICAL: 2,
		FAILED: 3
	};

	const cmpBladeQ = useQuery(api.sim.queries.getComponentTimeseries, () =>
		runId ? { runId, componentId: 'blade' as const } : 'skip'
	);
	const cmpRailQ = useQuery(api.sim.queries.getComponentTimeseries, () =>
		runId ? { runId, componentId: 'rail' as const } : 'skip'
	);
	const cmpNozzleQ = useQuery(api.sim.queries.getComponentTimeseries, () =>
		runId ? { runId, componentId: 'nozzle' as const } : 'skip'
	);
	const cmpCleaningQ = useQuery(api.sim.queries.getComponentTimeseries, () =>
		runId ? { runId, componentId: 'cleaning' as const } : 'skip'
	);
	const cmpHeaterQ = useQuery(api.sim.queries.getComponentTimeseries, () =>
		runId ? { runId, componentId: 'heater' as const } : 'skip'
	);
	const cmpSensorQ = useQuery(api.sim.queries.getComponentTimeseries, () =>
		runId ? { runId, componentId: 'sensor' as const } : 'skip'
	);

	type CmpRow = { tick: number; status: string };
	function downsampleStatuses(rows: CmpRow[] | undefined, runHorizon: number): Status[] {
		if (!rows || rows.length === 0) return Array(BUCKETS).fill('FUNCTIONAL' as Status);
		const cells: Status[] = Array(BUCKETS).fill('FUNCTIONAL' as Status);
		const ranks: number[] = Array(BUCKETS).fill(0);
		for (const r of rows) {
			const b = Math.min(BUCKETS - 1, Math.floor((r.tick / Math.max(1, runHorizon)) * BUCKETS));
			const s = (r.status in STATUS_RANK ? r.status : 'FUNCTIONAL') as Status;
			const rank = STATUS_RANK[s];
			if (rank >= (ranks[b] ?? 0)) {
				ranks[b] = rank;
				cells[b] = s;
			}
		}
		return cells;
	}

	const realComponentMatrix = $derived.by(() => {
		if (!runId) return null;
		const byId: Record<string, CmpRow[] | undefined> = {
			blade: cmpBladeQ.data,
			rail: cmpRailQ.data,
			nozzle: cmpNozzleQ.data,
			cleaning: cmpCleaningQ.data,
			heater: cmpHeaterQ.data,
			sensor: cmpSensorQ.data
		};
		// Block until at least one query returns; rows that haven't loaded yet
		// just render as FUNCTIONAL filler in the meantime.
		const anyLoaded = Object.values(byId).some((r) => Array.isArray(r) && r.length > 0);
		if (!anyLoaded) return null;
		const horizon = Math.max(
			...Object.values(byId).map((rows) => {
				if (!rows || rows.length === 0) return 0;
				const last = rows[rows.length - 1];
				return last ? last.tick : 0;
			})
		);
		return COMPONENT_ROWS.map((row) => ({
			...row,
			cells: downsampleStatuses(byId[row.id], horizon)
		}));
	});

	const componentMatrix = $derived(realComponentMatrix ?? syntheticComponentMatrix);

	// Status snapshot — pinned to NP-003 at NOW (matches Phoenix scenario)
	const snapshot = {
		code: 'NP-003',
		label: 'nozzle',
		health: 0,
		status: 'FAILED' as Status,
		rulDelta: -38
	};

	// Cell hover for tooltip
	type GridHover = {
		rowId: string;
		rowLabel: string;
		rowCode: string;
		bucket: number;
		status: Status;
		clientX: number;
		clientY: number;
	};
	let gridHover = $state<GridHover | null>(null);
	let gridEl = $state<HTMLDivElement | null>(null);

	function handleCellEnter(e: MouseEvent, row: (typeof componentMatrix)[number], bucket: number) {
		if (!gridEl) return;
		const rect = gridEl.getBoundingClientRect();
		gridHover = {
			rowId: row.id,
			rowLabel: row.label,
			rowCode: row.code,
			bucket,
			status: row.cells[bucket] ?? 'FUNCTIONAL',
			clientX: e.clientX - rect.left,
			clientY: e.clientY - rect.top
		};
	}
	function handleCellLeave() {
		gridHover = null;
	}

	// X axis tick labels for the degradation grid
	function bucketToTimeLabel(b: number): string {
		if (b === 0) return 'T₀';
		if (b === 16) return 'T+24h';
		if (b === NOW_BUCKET) return $t('sim_ui.driver_coupled_decay.now');
		if (b === 48) return 'T+72h';
		if (b === BUCKETS - 1) return 'Tₙ';
		return '';
	}

	function statusLabel(status: Status | AlertSeverity): string {
		return $t(`sim_ui.status.${status.toLowerCase()}`);
	}

	function componentLabel(component: ComponentId): string {
		return $t(`sim_ui.components.${component}`);
	}
</script>

<section class="dcd">
	<!-- ────────── TOP: Phase 2 — Driver streams + Proactive alerts (shared time window) ────────── -->
	<div class="dcd-block">
		<header class="dcd-head">
			<div class="dcd-eyebrow">{$t('sim_ui.driver_coupled_decay.top.eyebrow')}</div>
			<h2 class="dcd-title">{$t('sim_ui.driver_coupled_decay.top.title')}</h2>
			<p class="dcd-sub">
				{$t('sim_ui.driver_coupled_decay.top.description')}
			</p>
		</header>

		<div class="dcd-window-meta">
			{$t('sim_ui.driver_coupled_decay.top.showing_tick')} <span class="dcd-mono">{startTick}</span>
			→
			<span class="dcd-mono">{Math.max(startTick, endTick - 1)}</span>
			{$t('sim_ui.driver_coupled_decay.top.of')} <span class="dcd-mono">{HORIZON}</span>
			<span class="dcd-meta-sep">·</span>
			{$t('sim_ui.driver_coupled_decay.top.window')} <span class="dcd-mono">{windowLabel}</span>
			<span class="dcd-meta-sep">·</span>
			{$t('sim_ui.driver_coupled_decay.top.alerts_in_window')}
			<span class="dcd-mono">{visibleAlerts.length}</span>
			/
			<span class="dcd-mono">{alertsList.length}</span>
		</div>

		<div class="dcd-block-split dcd-block-split-inner">
			<div class="dcd-split-col">
				<div class="dcd-section-label">{$t('sim_ui.driver_coupled_decay.top.driver_streams')}</div>

				<div class="dcd-sparks">
					{#each visibleDriverData as d (d.id)}
						<div class="dcd-spark-strip">
							<div class="dcd-spark-label">{$t(d.labelKey)}</div>
							<div class="dcd-spark-chart-wrap">
								<svg
									bind:this={sparkRefs[d.id]}
									class="dcd-spark-svg"
									viewBox={`0 0 ${sparkW} ${sparkH}`}
									preserveAspectRatio="none"
									role="img"
									aria-label={$t(d.labelKey)}
									onmousemove={(e) => handleSparkMove(e, d)}
									onmouseleave={handleSparkLeave}
								>
									<g transform={`translate(${sparkPadX}, ${sparkPadY})`}>
										<path class="dcd-spark-line" d={sparkLine(d.data) ?? ''} />
										{#if sparkHover && sparkHover.driverId === d.id}
											<line
												class="dcd-spark-guide"
												x1={xSpark(sparkHover.tick)}
												x2={xSpark(sparkHover.tick)}
												y1="0"
												y2={sparkInnerH}
											/>
											<circle
												class="dcd-spark-dot"
												cx={xSpark(sparkHover.tick)}
												cy={ySpark(sparkHover.v)}
												r="3"
											/>
										{/if}
										<rect
											class="dcd-spark-capture"
											x="0"
											y="0"
											width={sparkInnerW}
											height={sparkInnerH}
										/>
									</g>
								</svg>
								<span class="dcd-spark-value">{fmtPct(d.data[d.data.length - 1]?.v ?? 0)}</span>

								{#if sparkHover && sparkHover.driverId === d.id}
									<div
										class="dcd-spark-tip"
										style:left="{Math.min(sparkHover.clientX + 12, 420)}px"
										style:top="{Math.max(sparkHover.clientY - 44, -28)}px"
									>
										<div class="dcd-tip-row">
											<span class="dcd-tip-key"
												>{$t('sim_ui.driver_coupled_decay.tooltip.tick')}</span
											>
											<span class="dcd-tip-val">{sparkHover.tick}</span>
										</div>
										<div class="dcd-tip-row">
											<span class="dcd-tip-key">{$t(d.labelKey)}</span>
											<span class="dcd-tip-val">{sparkHover.v.toFixed(3)}</span>
										</div>
									</div>
								{/if}
							</div>
						</div>
					{/each}
				</div>

				<p class="dcd-foot">{$t('sim_ui.driver_coupled_decay.top.latest_value_foot')}</p>
			</div>

			<div class="dcd-split-col">
				<div class="dcd-section-label">
					{$t('sim_ui.driver_coupled_decay.top.proactive_alerts')}
				</div>

				<ul class="dcd-alerts">
					{#if visibleAlerts.length === 0}
						<li class="dcd-alerts-empty">{$t('sim_ui.driver_coupled_decay.top.no_alerts')}</li>
					{/if}
					{#each visibleAlerts as a, i (i)}
						<li class="dcd-alert-row">
							<span
								class="dcd-alert-icon"
								class:is-failed={a.status === 'FAILED'}
								class:is-critical={a.status === 'CRITICAL'}
								class:is-degraded={a.status === 'DEGRADED'}
								style:--icon-color={SEVERITY_COLOR[a.status]}
								aria-hidden="true"
							></span>
							<span class="dcd-alert-tick"
								>{$t('sim_ui.driver_coupled_decay.top.tick')} {a.tick}</span
							>
							<span class="dcd-alert-component">{componentLabel(a.component)}</span>
							<span class="dcd-alert-arrow">→</span>
							<span class="dcd-alert-status" style:color={SEVERITY_COLOR[a.status]}>
								{statusLabel(a.status)}
							</span>
							<span class="dcd-alert-driver-label"
								>· {$t('sim_ui.driver_coupled_decay.top.top_driver')}</span
							>
							<code class="dcd-alert-driver-pill"
								>{a.topDriverKey} = {fmtDriverValue(a.topDriverValue)}</code
							>
						</li>
					{/each}
				</ul>

				<p class="dcd-foot">
					{$t('sim_ui.driver_coupled_decay.top.alerts_foot')}
				</p>
			</div>
		</div>
	</div>

	<!-- ────────── BOTTOM: Driver-coupled component decay ────────── -->
	<div class="dcd-block dcd-block-grid">
		<header class="dcd-head">
			<div class="dcd-eyebrow">{$t('sim_ui.driver_coupled_decay.bottom.eyebrow')}</div>
			<h2 class="dcd-title">{$t('sim_ui.driver_coupled_decay.bottom.title')}</h2>
			<div class="dcd-meta">
				<span
					><span class="dcd-meta-key">{$t('sim_ui.driver_coupled_decay.bottom.meta.run')}</span> 2041</span
				>
				<span class="dcd-meta-sep">·</span>
				<span
					><span class="dcd-meta-key">{$t('sim_ui.driver_coupled_decay.bottom.meta.scenario')}</span
					> phoenix</span
				>
				<span class="dcd-meta-sep">·</span>
				<span
					><span class="dcd-meta-key">{$t('sim_ui.driver_coupled_decay.bottom.meta.horizon')}</span> 96h</span
				>
				<span class="dcd-meta-sep">·</span>
				<span
					><span class="dcd-meta-key"
						>{$t('sim_ui.driver_coupled_decay.bottom.meta.resolution')}</span
					> 15min</span
				>
				<span class="dcd-meta-sep">·</span>
				<span
					><span class="dcd-meta-key">{$t('sim_ui.driver_coupled_decay.bottom.meta.engine')}</span>
					{$t('sim_ui.driver_coupled_decay.bottom.meta.engine_value')}</span
				>
			</div>
		</header>

		<div class="dcd-grid-section">
			<div class="dcd-grid-section-head">
				<div class="dcd-section-label">
					{$t('sim_ui.driver_coupled_decay.bottom.component_degradation')}
				</div>
				<div class="dcd-section-sub">
					{$t('sim_ui.driver_coupled_decay.bottom.health_buckets_sub')}
				</div>
			</div>

			<div class="dcd-grid-wrap" bind:this={gridEl}>
				<div class="dcd-grid-rows">
					{#each componentMatrix as row (row.id)}
						<div class="dcd-grid-row">
							<div class="dcd-row-label">
								<div class="dcd-row-label-name">{row.label}</div>
								<div class="dcd-row-label-code">{row.code} · {row.subsystem}</div>
							</div>
							<div class="dcd-row-cells">
								{#each row.cells as status, b (b)}
									<div
										class="dcd-cell"
										role="presentation"
										style:background={STATUS_COLORS[status]}
										onmouseenter={(e) => handleCellEnter(e, row, b)}
										onmousemove={(e) => handleCellEnter(e, row, b)}
										onmouseleave={handleCellLeave}
									></div>
								{/each}
							</div>
						</div>
					{/each}
				</div>

				<!-- NOW marker — overlays the rows -->
				<div class="dcd-now-line" style:left="{(NOW_BUCKET / BUCKETS) * 100}%">
					<span class="dcd-now-pill">{$t('sim_ui.driver_coupled_decay.now')}</span>
				</div>

				<!-- X axis labels -->
				<div class="dcd-x-axis">
					{#each Array(BUCKETS) as _, b (b)}
						{@const lbl = bucketToTimeLabel(b)}
						{#if lbl}
							<div class="dcd-x-label" style:left="{((b + 0.5) / BUCKETS) * 100}%">
								{lbl}
							</div>
						{/if}
					{/each}
				</div>

				<!-- Status snapshot callout -->
				<div class="dcd-snapshot" style:left="{(NOW_BUCKET / BUCKETS) * 100}%">
					<div class="dcd-snapshot-arrow"></div>
					<div class="dcd-snapshot-card">
						<div class="dcd-snapshot-title">
							<span class="dcd-snapshot-label"
								>{$t('sim_ui.driver_coupled_decay.bottom.status_snapshot')}</span
							>
							<span class="dcd-snapshot-sep">·</span>
							<span class="dcd-snapshot-code">{snapshot.code}</span>
						</div>
						<div class="dcd-snapshot-body">
							{$t('sim_ui.driver_coupled_decay.bottom.health')} <strong>{snapshot.health}%</strong>
							<span class="dcd-snapshot-sep">·</span>
							<strong>{statusLabel(snapshot.status)}</strong>
							<span class="dcd-snapshot-sep">·</span>
							{$t('sim_ui.driver_coupled_decay.bottom.delta_rul')}
							<strong>{snapshot.rulDelta}%</strong>
						</div>
					</div>
				</div>

				{#if gridHover}
					<div
						class="dcd-grid-tip"
						style:left="{Math.min(gridHover.clientX + 14, 1100)}px"
						style:top="{Math.max(gridHover.clientY - 60, 0)}px"
					>
						<div class="dcd-tip-row">
							<span class="dcd-tip-key"
								>{$t('sim_ui.driver_coupled_decay.tooltip.component_id')}</span
							>
							<span class="dcd-tip-val">{gridHover.rowId}</span>
						</div>
						<div class="dcd-tip-row">
							<span class="dcd-tip-key">{$t('sim_ui.driver_coupled_decay.tooltip.code')}</span>
							<span class="dcd-tip-val">{gridHover.rowCode}</span>
						</div>
						<div class="dcd-tip-row">
							<span class="dcd-tip-key">{$t('sim_ui.driver_coupled_decay.tooltip.bucket')}</span>
							<span class="dcd-tip-val">{gridHover.bucket}</span>
						</div>
						<div class="dcd-tip-row">
							<span class="dcd-tip-key">{$t('sim_ui.driver_coupled_decay.tooltip.status')}</span>
							<span class="dcd-tip-val" style:color={STATUS_COLORS[gridHover.status]}>
								{statusLabel(gridHover.status)}
							</span>
						</div>
					</div>
				{/if}
			</div>
		</div>

		<footer class="dcd-grid-foot">
			<div class="dcd-legend">
				<span class="dcd-legend-key"
					>{$t('sim_ui.driver_coupled_decay.bottom.legend_health_bucket')}</span
				>
				{#each Object.entries(STATUS_COLORS) as [status, color] (status)}
					<span class="dcd-legend-item">
						<span class="dcd-legend-sq" style:background={color}></span>
						<span class="dcd-legend-label">{statusLabel(status as Status)}</span>
					</span>
				{/each}
			</div>
			<div class="dcd-meta dcd-meta-right">
				<span
					><span class="dcd-meta-key"
						>{$t('sim_ui.driver_coupled_decay.bottom.footer_meta.model')}</span
					> v3.4.1</span
				>
				<span class="dcd-meta-sep">·</span>
				<span
					><span class="dcd-meta-key"
						>{$t('sim_ui.driver_coupled_decay.bottom.footer_meta.trained_on')}</span
					> 1.2M run-hours</span
				>
				<span class="dcd-meta-sep">·</span>
				<span
					><span class="dcd-meta-key"
						>{$t('sim_ui.driver_coupled_decay.bottom.footer_meta.last_calibration')}</span
					> 2026-04-02</span
				>
			</div>
		</footer>
	</div>
</section>

<style>
	.dcd {
		--accent: #024ad8;
		--fg: #000000;
		--fg-3: #5a5a5a;
		--fg-4: #8a8a8a;
		--line: #e6e6e6;
		--surface: #ffffff;
		--sans: 'Wix Madefor Text', 'HP Simplified', 'Helvetica Neue', Helvetica, Arial, sans-serif;
		--display:
			'Wix Madefor Display', 'HP Simplified', 'Helvetica Neue', Helvetica, Arial, sans-serif;

		max-width: 1280px;
		margin: 0 auto;
		padding: 16px 40px 56px;
		font-family: var(--sans);
		color: var(--fg);
	}

	.dcd-block {
		padding: 32px 0;
		border-top: 1px solid var(--line);
	}
	.dcd-block:first-child {
		border-top: none;
	}

	.dcd-head {
		margin-bottom: 16px;
	}
	.dcd-eyebrow {
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.16em;
		color: var(--accent);
		text-transform: uppercase;
		margin-bottom: 6px;
	}
	.dcd-title {
		font-family: var(--display);
		font-size: clamp(22px, 2.4vw, 30px);
		font-weight: 800;
		letter-spacing: -0.025em;
		margin: 0;
		color: var(--fg);
	}
	.dcd-meta {
		margin-top: 10px;
		display: flex;
		flex-wrap: wrap;
		gap: 6px 10px;
		font-size: 11px;
		color: var(--fg-3);
		letter-spacing: 0.04em;
		font-weight: 400;
	}
	.dcd-meta-right {
		justify-content: flex-end;
	}
	.dcd-meta-key {
		font-weight: 700;
		color: var(--fg);
		letter-spacing: 0.1em;
		text-transform: uppercase;
		margin-right: 4px;
		font-size: 10px;
	}
	.dcd-meta-sep {
		color: var(--fg-4);
	}

	/* ─── Top split: Driver streams (left) + Alerts feed (right) ─── */
	.dcd-block-split {
		display: grid;
		grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
		gap: 40px;
		align-items: start;
	}
	.dcd-block-split-inner {
		margin-top: 18px;
	}
	.dcd-split-col {
		min-width: 0;
	}
	@media (max-width: 900px) {
		.dcd-block-split {
			grid-template-columns: 1fr;
			gap: 32px;
		}
	}

	/* ─── Header sub-line + window meta strip (Phase 2) ─── */
	.dcd-sub {
		margin: 6px 0 0;
		font-size: 12px;
		color: var(--fg-3);
		max-width: 56ch;
	}
	.dcd-window-meta {
		margin-top: 12px;
		font-size: 11px;
		color: var(--fg-3);
		letter-spacing: 0.04em;
	}
	.dcd-mono {
		font-family: ui-monospace, 'SF Mono', 'Menlo', 'Consolas', monospace;
		color: var(--fg);
		font-weight: 600;
		font-variant-numeric: tabular-nums;
	}

	/* ─── Empty state for the alerts list ─── */
	.dcd-alerts-empty {
		font-size: 12px;
		color: var(--fg-4);
		font-style: italic;
		padding: 16px 0;
		list-style: none;
	}

	/* ─── Sparklines ─── */
	.dcd-sparks {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.dcd-spark-strip {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.dcd-spark-label {
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.12em;
		color: var(--fg);
		text-transform: uppercase;
	}
	.dcd-spark-chart-wrap {
		position: relative;
		display: flex;
		align-items: center;
	}
	.dcd-spark-svg {
		flex: 1;
		width: 100%;
		height: 40px;
		display: block;
	}
	.dcd-spark-line {
		fill: none;
		stroke: #0a0a0a;
		stroke-width: 1.4;
		stroke-linejoin: round;
	}
	.dcd-spark-guide {
		stroke: var(--accent);
		stroke-width: 1;
		stroke-dasharray: 2 3;
		opacity: 0.6;
		pointer-events: none;
	}
	.dcd-spark-dot {
		fill: var(--accent);
		pointer-events: none;
	}
	.dcd-spark-capture {
		fill: transparent;
		pointer-events: all;
		cursor: crosshair;
	}
	.dcd-spark-value {
		position: absolute;
		right: 4px;
		bottom: 6px;
		color: var(--accent);
		font-size: 13px;
		font-weight: 700;
		font-feature-settings: 'tnum' 1;
		pointer-events: none;
	}
	.dcd-spark-tip {
		position: absolute;
		min-width: 180px;
		padding: 8px 12px;
		background: #ffffff;
		border: 1px solid #d4d4d4;
		border-radius: 8px;
		box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
		font-size: 12px;
		pointer-events: none;
		z-index: 20;
	}

	.dcd-tip-row {
		display: flex;
		justify-content: space-between;
		gap: 16px;
		padding: 2px 0;
	}
	.dcd-tip-key {
		color: var(--fg-3);
	}
	.dcd-tip-val {
		color: var(--fg);
		font-weight: 700;
		font-feature-settings: 'tnum' 1;
	}

	.dcd-foot {
		margin: 18px 0 0;
		font-size: 13px;
		color: var(--fg-3);
		line-height: 1.5;
	}

	/* ─── Proactive alerts feed ─── */
	.dcd-alerts-sub {
		margin: 8px 0 0;
		font-size: 13px;
		color: var(--fg-3);
		line-height: 1.5;
	}
	.dcd-alerts {
		list-style: none;
		/* No top margin — section label sits flush above the box, matching
		   the streams column where the first sparkline strip butts up
		   against `DRIVER STREAMS`. Keeps both columns starting at the
		   same Y position. */
		margin: 4px 0 0;
		padding: 0;
		border: 1px solid var(--line);
		border-radius: 8px;
		background: var(--surface);
		max-height: 360px;
		overflow-y: auto;
		overscroll-behavior: contain;
	}
	/* subtle scrollbar */
	.dcd-alerts::-webkit-scrollbar {
		width: 6px;
	}
	.dcd-alerts::-webkit-scrollbar-thumb {
		background: var(--line);
		border-radius: 3px;
	}
	.dcd-alerts::-webkit-scrollbar-thumb:hover {
		background: var(--fg-4);
	}
	.dcd-alert-row {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 10px 14px;
		border-top: 1px solid var(--line);
		font-size: 12px;
		flex-wrap: wrap;
	}
	.dcd-alert-row:first-child {
		border-top: none;
	}
	.dcd-alert-icon {
		flex-shrink: 0;
		width: 12px;
		height: 12px;
		border-radius: 50%;
		background: var(--icon-color, var(--accent));
	}
	.dcd-alert-icon.is-critical {
		background: linear-gradient(
			to right,
			var(--icon-color) 0 50%,
			color-mix(in srgb, var(--icon-color) 25%, #ffffff) 50% 100%
		);
		border: 1px solid var(--icon-color);
	}
	.dcd-alert-icon.is-degraded {
		background: linear-gradient(
			to right,
			var(--icon-color) 0 50%,
			color-mix(in srgb, var(--icon-color) 25%, #ffffff) 50% 100%
		);
		border: 1px solid var(--icon-color);
	}
	.dcd-alert-tick {
		min-width: 64px;
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.1em;
		color: var(--fg-3);
		text-transform: uppercase;
	}
	.dcd-alert-component {
		font-size: 12px;
		font-weight: 700;
		color: var(--fg);
		letter-spacing: 0.04em;
	}
	.dcd-alert-arrow {
		color: var(--fg-4);
	}
	.dcd-alert-status {
		font-size: 11px;
		font-weight: 700;
		letter-spacing: 0.1em;
	}
	.dcd-alert-driver-label {
		color: var(--fg-3);
		font-size: 12px;
	}
	.dcd-alert-driver-pill {
		font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-size: 11px;
		color: var(--fg);
		background: #f4f4f5;
		border: 1px solid var(--line);
		border-radius: 4px;
		padding: 2px 6px;
		font-feature-settings: 'tnum' 1;
		white-space: nowrap;
	}

	/* ─── Component degradation grid ─── */
	.dcd-block-grid {
		padding-top: 32px;
	}
	.dcd-grid-section {
		margin-top: 8px;
	}
	.dcd-grid-section-head {
		margin-bottom: 12px;
	}
	.dcd-section-label {
		font-size: 11px;
		font-weight: 700;
		letter-spacing: 0.14em;
		color: var(--fg);
	}
	.dcd-section-sub {
		font-size: 11px;
		color: var(--fg-4);
		margin-top: 2px;
	}

	.dcd-grid-wrap {
		position: relative;
		padding-bottom: 100px; /* room for x axis + snapshot */
	}
	.dcd-grid-rows {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.dcd-grid-row {
		display: grid;
		grid-template-columns: 160px 1fr;
		gap: 12px;
		align-items: center;
	}
	.dcd-row-label {
		display: flex;
		flex-direction: column;
		gap: 1px;
		text-align: right;
		padding-right: 4px;
	}
	.dcd-row-label-name {
		font-size: 12px;
		font-weight: 700;
		color: var(--fg);
	}
	.dcd-row-label-code {
		font-size: 10px;
		color: var(--fg-4);
		letter-spacing: 0.04em;
	}
	.dcd-row-cells {
		display: grid;
		grid-template-columns: repeat(64, 1fr);
		gap: 1px;
		height: 22px;
	}
	.dcd-cell {
		height: 100%;
		border: none;
		padding: 0;
		cursor: pointer;
		transition: outline-color 0.1s;
		outline: 1px solid transparent;
		outline-offset: -1px;
	}
	.dcd-cell:hover {
		outline-color: var(--accent);
	}

	/* NOW marker */
	.dcd-now-line {
		position: absolute;
		top: 0;
		bottom: 60px;
		width: 2px;
		background: var(--accent);
		/* Account for the 160px label column + 12px gap on the left */
		margin-left: 172px;
		transform: translateX(-1px);
		pointer-events: none;
	}
	.dcd-now-line {
		left: calc(172px + (100% - 172px) * 0.5);
	}
	.dcd-now-pill {
		position: absolute;
		bottom: -22px;
		left: 50%;
		transform: translateX(-50%);
		padding: 2px 8px;
		background: var(--accent);
		color: #ffffff;
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.1em;
	}

	/* X axis labels under the grid */
	.dcd-x-axis {
		position: absolute;
		left: 172px;
		right: 0;
		bottom: 36px;
		height: 16px;
	}
	.dcd-x-label {
		position: absolute;
		transform: translateX(-50%);
		font-size: 10px;
		color: var(--fg-3);
		letter-spacing: 0.06em;
		white-space: nowrap;
	}

	/* Status snapshot callout */
	.dcd-snapshot {
		position: absolute;
		bottom: -8px;
		transform: translateX(8px);
		max-width: 360px;
	}
	.dcd-snapshot-card {
		padding: 10px 14px;
		background: #ffffff;
		border: 1.5px solid var(--accent);
		border-radius: 4px;
		box-shadow: 0 4px 14px rgba(2, 74, 216, 0.12);
		font-size: 12px;
	}
	.dcd-snapshot-title {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--fg);
		margin-bottom: 4px;
	}
	.dcd-snapshot-label {
		color: var(--fg);
	}
	.dcd-snapshot-code {
		color: var(--accent);
	}
	.dcd-snapshot-sep {
		color: var(--fg-4);
		margin: 0 2px;
	}
	.dcd-snapshot-body {
		font-size: 13px;
		color: var(--fg-3);
	}
	.dcd-snapshot-body strong {
		color: var(--fg);
		font-weight: 700;
	}

	.dcd-grid-tip {
		position: absolute;
		min-width: 200px;
		padding: 10px 14px;
		background: #ffffff;
		border: 1px solid #d4d4d4;
		border-radius: 8px;
		box-shadow: 0 8px 20px rgba(0, 0, 0, 0.1);
		font-size: 12px;
		pointer-events: none;
		z-index: 20;
	}

	/* Footer with legend */
	.dcd-grid-foot {
		margin-top: 24px;
		padding-top: 16px;
		border-top: 1px solid var(--line);
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: center;
		gap: 16px;
	}
	.dcd-legend {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px 14px;
	}
	.dcd-legend-key {
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.14em;
		color: var(--fg-4);
	}
	.dcd-legend-item {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 11px;
		color: var(--fg);
	}
	.dcd-legend-sq {
		width: 12px;
		height: 12px;
		display: inline-block;
		border: 1px solid var(--line);
	}
</style>
