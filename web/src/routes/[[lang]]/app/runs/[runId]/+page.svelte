<script lang="ts">
	import { page } from '$app/state';
	import { getTranslate } from '@tolgee/svelte';
	import { useQuery } from 'convex-svelte';
	import { api } from '$lib/convex/_generated/api';
	import type { Id } from '$lib/convex/_generated/dataModel';
	import { onMount } from 'svelte';
	import SEOHead from '$lib/components/SEOHead.svelte';
	import { scaleLinear } from 'd3-scale';
	import { line as d3Line } from 'd3-shape';

	const { t } = getTranslate();

	const COMPONENT_IDS = ['blade', 'rail', 'nozzle', 'cleaning', 'heater', 'sensor'] as const;
	type ComponentId = (typeof COMPONENT_IDS)[number];

	const componentColor: Record<ComponentId, string> = {
		blade: '#6366f1',
		rail: '#0ea5e9',
		nozzle: '#f97316',
		cleaning: '#14b8a6',
		heater: '#ef4444',
		sensor: '#a855f7'
	};

	const runId = $derived(page.params.runId as Id<'simRuns'>);

	// Reactive run summary + per-component time series.
	const summaryQuery = useQuery(api.sim.queries.getRunSummary, () => ({ runId }));
	const summary = $derived(summaryQuery.data);

	// One useQuery per component — Convex deduplicates, and the alternative
	// (one query returning 1560 rows) would dominate the wire payload.
	const seriesByComp = $derived(
		COMPONENT_IDS.map((cid) => ({
			cid,
			query: useQuery(api.sim.queries.getComponentTimeseries, () => ({
				runId,
				componentId: cid
			}))
		}))
	);

	const eventsQuery = useQuery(api.sim.queries.listEvents, () => ({ runId, limit: 500 }));

	const horizon = $derived(summary?.horizonTicks ?? 0);
	const lastTick = $derived(summary?.lastTick ?? 0);

	let currentTick = $state(0);
	let isPlaying = $state(false);
	let playbackSpeedMs = $state(50); // ms per tick at 1x

	// Clamp currentTick to [0, lastTick] whenever data lands.
	$effect(() => {
		if (currentTick > lastTick) currentTick = lastTick;
	});

	let intervalId: ReturnType<typeof setInterval> | null = null;
	$effect(() => {
		if (intervalId) {
			clearInterval(intervalId);
			intervalId = null;
		}
		if (isPlaying && lastTick > 0) {
			intervalId = setInterval(() => {
				if (currentTick >= lastTick) {
					isPlaying = false;
				} else {
					currentTick = Math.min(lastTick, currentTick + 1);
				}
			}, playbackSpeedMs);
		}
		return () => {
			if (intervalId) clearInterval(intervalId);
		};
	});

	function statusColor(status: string | null | undefined): string {
		switch (status) {
			case 'FUNCTIONAL':
				return 'bg-emerald-500';
			case 'DEGRADED':
				return 'bg-yellow-500';
			case 'CRITICAL':
				return 'bg-orange-500';
			case 'FAILED':
				return 'bg-red-600';
			default:
				return 'bg-zinc-400';
		}
	}

	function statusLabel(status: string | null | undefined): string {
		if (!status) return '—';
		return $t(`sim_ui.status.${status.toLowerCase()}`);
	}

	function componentLabel(cid: ComponentId): string {
		return $t(`sim_ui.components.${cid}`);
	}

	// ------------ Resolved scenario config (Setup card) ------------

	type Driver = { kind?: string; [k: string]: unknown };
	type ResolvedConfig = {
		run?: { seed?: number; horizon_ticks?: number; dt_seconds?: number };
		environment?: {
			base_ambient_C?: number;
			amplitude_C?: number;
			weekly_runtime_hours?: number;
			vibration_level?: number;
		};
		drivers?: {
			temperature_stress?: Driver;
			humidity_contamination?: Driver;
			operational_load?: Driver;
			maintenance_level?: Driver & { schedule?: Array<{ tick: number; value: number }> };
		};
		[k: string]: unknown;
	};

	function isResolvedConfig(x: unknown): x is ResolvedConfig {
		if (!x || typeof x !== 'object') return false;
		const o = x as Record<string, unknown>;
		return (
			typeof o.environment === 'object' &&
			o.environment !== null &&
			typeof o.drivers === 'object' &&
			o.drivers !== null
		);
	}

	const setup = $derived.by<ResolvedConfig | null>(() => {
		if (!summary?.scenarioConfig) return null;
		let parsed: unknown;
		try {
			parsed = JSON.parse(summary.scenarioConfig);
		} catch {
			return null;
		}
		return isResolvedConfig(parsed) ? parsed : null;
	});

	const DRIVER_PARAM_KEYS = [
		'base',
		'amplitude',
		'mean',
		'theta',
		'sigma',
		'period_weeks'
	] as const;
	function driverSummary(d: Driver | undefined): string {
		if (!d) return '—';
		const params = DRIVER_PARAM_KEYS.filter((k) => typeof d[k] === 'number')
			.slice(0, 3)
			.map((k) => `${k} ${(d[k] as number).toFixed(2)}`)
			.join(', ');
		const kind = d.kind ?? 'unknown';
		return params ? `${kind} (${params})` : kind;
	}

	type SeriesRow = { tick: number; healthIndex: number; status: string };

	function snapshotAt(rows: SeriesRow[] | undefined, tick: number): SeriesRow | null {
		if (!rows || rows.length === 0) return null;
		// rows are sorted by tick asc; find the largest row.tick <= tick.
		let best: SeriesRow | null = null;
		for (const r of rows) {
			if (r.tick <= tick) best = r;
			else break;
		}
		return best ?? rows[0] ?? null;
	}

	// Chart geometry
	const chartWidth = 720;
	const chartHeight = 240;
	const margin = { top: 12, right: 24, bottom: 24, left: 36 };
	const innerW = chartWidth - margin.left - margin.right;
	const innerH = chartHeight - margin.top - margin.bottom;

	const xScale = $derived(
		scaleLinear()
			.domain([0, Math.max(1, horizon - 1)])
			.range([0, innerW])
	);
	const yScale = $derived(scaleLinear().domain([0, 1]).range([innerH, 0]));

	const linePath = $derived((rows: SeriesRow[]) => {
		const gen = d3Line<SeriesRow>()
			.x((d) => xScale(d.tick))
			.y((d) => yScale(d.healthIndex));
		return gen(rows) ?? '';
	});

	// X-axis ticks: 5 evenly spaced labels.
	const xTicks = $derived.by(() => {
		const n = 5;
		const max = Math.max(0, horizon - 1);
		return Array.from({ length: n }, (_, i) => Math.round((i / (n - 1)) * max));
	});

	onMount(() => {
		// Auto-jump to last tick on load so the page isn't blank.
		if (lastTick > 0 && currentTick === 0) currentTick = lastTick;
	});
</script>

<SEOHead
	title={summary
		? `${$t('sim_ui.run_detail.run_prefix')} ${summary.scenarioName}`
		: $t('sim_ui.run_detail.page_title')}
/>

<div class="mx-auto max-w-5xl space-y-6 p-6">
	{#if summaryQuery.isLoading}
		<div class="text-sm text-muted-foreground">{$t('sim_ui.run_detail.loading_run')}</div>
	{:else if !summary}
		<div class="rounded-md border border-destructive/40 bg-destructive/5 p-4 text-sm">
			{$t('sim_ui.run_detail.not_found')}
		</div>
	{:else}
		<!-- Header -->
		<header class="flex flex-wrap items-baseline justify-between gap-3">
			<div>
				<h1 class="text-2xl font-semibold">{summary.scenarioName}</h1>
				<p class="text-sm text-muted-foreground">
					{$t('sim_ui.run_detail.run_id')}
					<code class="font-mono text-xs">{runId}</code>
					· {$t('sim_ui.run_detail.seed')}
					{summary.seed}
					· {$t('sim_ui.run_detail.horizon')}
					{summary.horizonTicks}
					{$t('sim_ui.run_detail.ticks')}
				</p>
			</div>
			<span
				class="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-wide"
			>
				<span class={`h-2 w-2 rounded-full ${statusColor(summary.status)}`}></span>
				{statusLabel(summary.status)}
			</span>
		</header>

		<!-- Setup (resolved scenario config) -->
		{#if setup}
			<section class="space-y-4 rounded-lg border bg-card p-4">
				<h2 class="text-sm font-semibold">Setup</h2>

				<!-- Climate -->
				<div>
					<h3 class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Climate</h3>
					<dl class="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
						<div class="flex items-baseline justify-between sm:block">
							<dt class="text-xs text-muted-foreground">Ambient</dt>
							<dd class="font-mono">
								{setup.environment?.base_ambient_C ?? '—'} °C
								{#if setup.environment?.amplitude_C != null}
									± {setup.environment.amplitude_C}
								{/if}
							</dd>
						</div>
						<div class="flex items-baseline justify-between sm:block">
							<dt class="text-xs text-muted-foreground">Runtime</dt>
							<dd class="font-mono">{setup.environment?.weekly_runtime_hours ?? '—'} h/week</dd>
						</div>
						<div class="flex items-baseline justify-between sm:block">
							<dt class="text-xs text-muted-foreground">Vibration</dt>
							<dd class="font-mono">{setup.environment?.vibration_level ?? '—'}</dd>
						</div>
					</dl>
				</div>

				<!-- Drivers -->
				{#if setup.drivers}
					<div>
						<h3 class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
							Drivers
						</h3>
						<dl class="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-sm md:grid-cols-2">
							<div class="flex flex-col">
								<dt class="text-xs text-muted-foreground">temperature_stress</dt>
								<dd class="font-mono">{driverSummary(setup.drivers.temperature_stress)}</dd>
							</div>
							<div class="flex flex-col">
								<dt class="text-xs text-muted-foreground">humidity_contamination</dt>
								<dd class="font-mono">{driverSummary(setup.drivers.humidity_contamination)}</dd>
							</div>
							<div class="flex flex-col">
								<dt class="text-xs text-muted-foreground">operational_load</dt>
								<dd class="font-mono">{driverSummary(setup.drivers.operational_load)}</dd>
							</div>
							<div class="flex flex-col">
								<dt class="text-xs text-muted-foreground">maintenance_level</dt>
								<dd class="font-mono">{driverSummary(setup.drivers.maintenance_level)}</dd>
							</div>
						</dl>
					</div>
				{/if}

				<!-- Maintenance schedule -->
				{#if setup.drivers?.maintenance_level?.schedule?.length}
					<div>
						<h3 class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
							Maintenance schedule
						</h3>
						<ul class="mt-2 space-y-0.5 font-mono text-sm">
							{#each setup.drivers.maintenance_level.schedule as step (step.tick)}
								<li>tick {step.tick} → {step.value}</li>
							{/each}
						</ul>
					</div>
				{/if}
			</section>
		{/if}

		<!-- Playback controls -->
		<section class="space-y-3 rounded-lg border bg-card p-4">
			<div class="flex items-center gap-3">
				<button
					type="button"
					class="rounded-md border px-3 py-1 text-sm font-medium hover:bg-accent"
					onclick={() => (isPlaying = !isPlaying)}
					disabled={lastTick === 0}
				>
					{isPlaying ? $t('sim_ui.run_detail.pause') : $t('sim_ui.run_detail.play')}
				</button>

				<button
					type="button"
					class="rounded-md border px-3 py-1 text-sm hover:bg-accent"
					onclick={() => {
						isPlaying = false;
						currentTick = 0;
					}}
				>
					{$t('sim_ui.run_detail.reset')}
				</button>

				<button
					type="button"
					class="rounded-md border px-3 py-1 text-sm hover:bg-accent"
					onclick={() => (currentTick = lastTick)}
				>
					{$t('sim_ui.run_detail.end')}
				</button>

				<label class="ml-auto flex items-center gap-2 text-sm">
					{$t('sim_ui.run_detail.speed')}
					<select
						class="rounded-md border bg-background px-2 py-1 text-sm"
						bind:value={playbackSpeedMs}
					>
						<option value={200}>0.25×</option>
						<option value={100}>0.5×</option>
						<option value={50}>1×</option>
						<option value={20}>2.5×</option>
						<option value={10}>5×</option>
					</select>
				</label>
			</div>

			<div class="flex items-center gap-3 text-sm">
				<span class="font-mono tabular-nums">{$t('sim_ui.run_detail.tick')} {currentTick}</span>
				<input
					type="range"
					class="flex-1"
					min={0}
					max={Math.max(0, lastTick)}
					bind:value={currentTick}
					oninput={() => (isPlaying = false)}
				/>
				<span class="font-mono text-xs text-muted-foreground">/ {lastTick}</span>
			</div>
		</section>

		<!-- Component cards -->
		<section class="grid grid-cols-2 gap-3 md:grid-cols-3">
			{#each COMPONENT_IDS as cid (cid)}
				{@const series = seriesByComp.find((s) => s.cid === cid)?.query.data as
					| SeriesRow[]
					| undefined}
				{@const snap = snapshotAt(series, currentTick)}
				<div class="rounded-lg border bg-card p-3">
					<div class="flex items-center justify-between">
						<h3 class="text-sm font-semibold">{componentLabel(cid)}</h3>
						<span
							class="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase"
						>
							<span class={`h-1.5 w-1.5 rounded-full ${statusColor(snap?.status)}`}></span>
							{statusLabel(snap?.status)}
						</span>
					</div>
					<div class="mt-2 h-2 overflow-hidden rounded-full bg-muted">
						<div
							class="h-full"
							style:width={`${(snap ? snap.healthIndex : 0) * 100}%`}
							style:background-color={componentColor[cid]}
						></div>
					</div>
					<p class="mt-1 font-mono text-xs tabular-nums text-muted-foreground">
						{$t('sim_ui.run_detail.health')}
						{snap ? snap.healthIndex.toFixed(3) : '—'}
					</p>
				</div>
			{/each}
		</section>

		<!-- Health timeseries -->
		<section class="rounded-lg border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">{$t('sim_ui.health_timeline.title')}</h2>
			<svg
				viewBox={`0 0 ${chartWidth} ${chartHeight}`}
				class="h-auto w-full"
				role="img"
				aria-labelledby="component-health-chart-title"
			>
				<title id="component-health-chart-title">{$t('sim_ui.run_detail.chart_time_series')}</title>
				<g transform={`translate(${margin.left},${margin.top})`}>
					<!-- Y gridlines -->
					{#each [0, 0.2, 0.45, 0.75, 1] as y (y)}
						<line
							x1={0}
							x2={innerW}
							y1={yScale(y)}
							y2={yScale(y)}
							stroke="currentColor"
							stroke-opacity="0.08"
						/>
						<text
							x={-6}
							y={yScale(y)}
							text-anchor="end"
							dominant-baseline="middle"
							class="fill-muted-foreground"
							font-size="10"
						>
							{y.toFixed(2)}
						</text>
					{/each}

					<!-- X axis ticks -->
					{#each xTicks as t (t)}
						<line
							x1={xScale(t)}
							x2={xScale(t)}
							y1={innerH}
							y2={innerH + 4}
							stroke="currentColor"
							stroke-opacity="0.3"
						/>
						<text
							x={xScale(t)}
							y={innerH + 16}
							text-anchor="middle"
							class="fill-muted-foreground"
							font-size="10"
						>
							{t}
						</text>
					{/each}

					<!-- Lines (clipped to currentTick so playback animates) -->
					{#each seriesByComp as { cid, query } (cid)}
						{@const rows = (query.data as SeriesRow[] | undefined) ?? []}
						{@const visible = rows.filter((r) => r.tick <= currentTick)}
						<path
							d={linePath(visible)}
							fill="none"
							stroke={componentColor[cid]}
							stroke-width="1.5"
						/>
					{/each}

					<!-- Cursor -->
					<line
						x1={xScale(currentTick)}
						x2={xScale(currentTick)}
						y1={0}
						y2={innerH}
						stroke="currentColor"
						stroke-opacity="0.4"
						stroke-dasharray="3 3"
					/>
				</g>
			</svg>

			<!-- Legend -->
			<div class="mt-2 flex flex-wrap gap-3 text-xs">
				{#each COMPONENT_IDS as cid (cid)}
					<span class="inline-flex items-center gap-1.5">
						<span class="h-2 w-3 rounded-sm" style:background-color={componentColor[cid]}></span>
						<span>{componentLabel(cid)}</span>
					</span>
				{/each}
			</div>
		</section>

		<!-- Recent events -->
		<section class="rounded-lg border bg-card p-4">
			<h2 class="mb-3 text-sm font-semibold">{$t('sim_ui.run_detail.maintenance_events')}</h2>
			{#if eventsQuery.isLoading}
				<div class="text-sm text-muted-foreground">{$t('sim_ui.common.loading')}</div>
			{:else}
				{@const events = (eventsQuery.data ?? []).filter(
					(e: { tick: number }) => e.tick <= currentTick
				)}
				{#if events.length === 0}
					<div class="text-sm text-muted-foreground">{$t('sim_ui.run_detail.no_events')}</div>
				{:else}
					<ul class="space-y-1 text-sm">
						{#each events
							.slice(-25)
							.reverse() as ev (`${ev.tick}-${ev.kind}-${ev.componentId ?? 'global'}`)}
							<li class="flex items-baseline gap-3 font-mono text-xs">
								<span class="tabular-nums text-muted-foreground">t={ev.tick}</span>
								<span class="rounded-sm border px-1.5 py-0.5 text-[10px] uppercase">{ev.kind}</span>
								<span
									>{ev.componentId
										? componentLabel(ev.componentId as ComponentId)
										: $t('sim_ui.run_detail.global')}</span
								>
							</li>
						{/each}
					</ul>
				{/if}
			{/if}
		</section>
	{/if}
</div>
