<script lang="ts">
	import type { BaseComponentProps } from '@json-render/svelte';
	import { BarChart } from 'layerchart';
	import * as Chart from '$lib/components/ui/chart/index.js';

	type BarChartProps = {
		title: string | null;
		description: string | null;
		data: Array<Record<string, unknown>>;
		xKey: string;
		yKey: string;
		color: string | null;
		height: number | null;
	};

	let { props }: BaseComponentProps<BarChartProps> = $props();

	const color = $derived(props.color ?? 'var(--chart-1)');

	const config: Chart.ChartConfig = $derived({
		[props.yKey]: { label: props.yKey, color }
	});

	const layerSeries = $derived([{ key: props.yKey, label: props.yKey, value: props.yKey, color }]);

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
			<BarChart
				data={props.data}
				x={props.xKey}
				y={props.yKey}
				series={layerSeries}
				orientation="vertical"
				axis={true}
			>
				{#snippet tooltip()}
					<Chart.Tooltip />
				{/snippet}
			</BarChart>
		</Chart.Container>
	{/if}
</div>
