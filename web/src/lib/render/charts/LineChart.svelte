<script lang="ts">
	import type { BaseComponentProps } from '@json-render/svelte';
	import { LineChart, Spline, Rule } from 'layerchart';
	import { scaleLinear } from 'd3-scale';
	import * as Chart from '$lib/components/ui/chart/index.js';

	type Series = { key: string; label: string; color: string | null };
	type Event = { tick: number; label: string; color: string | null };

	type LineChartProps = {
		title: string | null;
		description: string | null;
		data: Array<Record<string, unknown>>;
		xKey: string;
		series: Series[];
		yMin: number | null;
		yMax: number | null;
		events: Event[] | null;
		height: number | null;
	};

	let { props }: BaseComponentProps<LineChartProps> = $props();

	const config: Chart.ChartConfig = $derived(
		Object.fromEntries(
			props.series.map((s, i) => [
				s.key,
				{ label: s.label, color: s.color ?? `var(--chart-${(i % 5) + 1})` }
			])
		)
	);

	const layerSeries = $derived(
		props.series.map((s, i) => ({
			key: s.key,
			label: s.label,
			value: s.key,
			color: s.color ?? `var(--chart-${(i % 5) + 1})`
		}))
	);

	const yDomain = $derived.by<[number, number] | undefined>(() => {
		if (props.yMin !== null && props.yMax !== null) return [props.yMin, props.yMax];
		if (props.data.length === 0) return [0, 1];
		// Default: 0..1 if all values fit, else min/max from data.
		let min = Infinity;
		let max = -Infinity;
		for (const row of props.data) {
			for (const s of props.series) {
				const v = row[s.key];
				if (typeof v !== 'number') continue;
				if (v < min) min = v;
				if (v > max) max = v;
			}
		}
		if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
		if (min >= 0 && max <= 1) return [0, 1];
		return [min, max];
	});

	const heightClass = $derived(props.height && props.height > 0 ? '' : 'aspect-video');
	const heightStyle = $derived(
		props.height && props.height > 0 ? `height: ${props.height}px;` : ''
	);
</script>

<div class="w-full">
	{#if props.title}
		<div class="mb-2 text-sm font-medium">{props.title}</div>
	{/if}
	{#if props.description}
		<div class="mb-2 text-xs text-muted-foreground">{props.description}</div>
	{/if}

	{#if props.data.length === 0}
		<Chart.Container {config} class="{heightClass} w-full" style={heightStyle}>
			<div class="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
				No data
			</div>
		</Chart.Container>
	{:else}
		<Chart.Container {config} class="{heightClass} w-full" style={heightStyle}>
			<LineChart
				data={props.data}
				x={props.xKey}
				series={layerSeries}
				xScale={scaleLinear()}
				yScale={scaleLinear()}
				{yDomain}
				axis={true}
				legend={props.series.length > 1}
			>
				{#snippet marks({ context })}
					{#each context.series.visibleSeries as s (s.key)}
						<Spline seriesKey={s.key} />
					{/each}
					{#each props.events ?? [] as ev, i (`${ev.tick}-${ev.label}-${i}`)}
						<Rule
							x={ev.tick}
							stroke={ev.color ?? 'currentColor'}
							stroke-dasharray="4 4"
							opacity={0.5}
						/>
					{/each}
				{/snippet}
				{#snippet tooltip()}
					<Chart.Tooltip />
				{/snippet}
			</LineChart>
		</Chart.Container>
	{/if}
</div>
