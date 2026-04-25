<script lang="ts">
	import { useQuery, useConvexClient } from 'convex-svelte';
	import { api } from '$lib/convex/_generated/api';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { localizedHref } from '$lib/utils/i18n';
	import SEOHead from '$lib/components/SEOHead.svelte';

	const SCENARIOS = [
		'barcelona-baseline',
		'phoenix-aggressive',
		'barcelona-with-events',
		'chaos-stress-test',
		'barcelona-human-disruption-no-maintenance',
		'barcelona-powder-bug-with-maintenance'
	] as const;

	const client = useConvexClient();
	const runsQuery = useQuery(api.sim.queries.listMyRuns, () => ({ limit: 100 }));

	let scenario = $state<(typeof SCENARIOS)[number]>('barcelona-baseline');
	let seed = $state<number | null>(null);
	let horizonTicks = $state<number | null>(null);
	let busy = $state(false);
	let errorMessage = $state<string | null>(null);

	async function startRun() {
		if (busy) return;
		busy = true;
		errorMessage = null;
		try {
			const args: { scenario: string; seed?: number; horizonTicks?: number } = { scenario };
			if (seed !== null && Number.isFinite(seed)) args.seed = seed;
			if (horizonTicks !== null && Number.isFinite(horizonTicks)) args.horizonTicks = horizonTicks;
			const result = (await client.action(api.sim.actions.runScenario, args)) as {
				runId: string;
			};
			await goto(resolve(localizedHref(`/app/runs/${result.runId}`)));
		} catch (err) {
			errorMessage = err instanceof Error ? err.message : String(err);
		} finally {
			busy = false;
		}
	}

	function statusColor(status: string): string {
		switch (status) {
			case 'running':
				return 'bg-sky-500';
			case 'completed':
				return 'bg-emerald-500';
			case 'failed':
				return 'bg-red-600';
			default:
				return 'bg-zinc-400';
		}
	}

	function fmtRelative(ts: number): string {
		const delta = Date.now() - ts;
		if (delta < 60_000) return `${Math.round(delta / 1000)}s ago`;
		if (delta < 3_600_000) return `${Math.round(delta / 60_000)}m ago`;
		if (delta < 86_400_000) return `${Math.round(delta / 3_600_000)}h ago`;
		return `${Math.round(delta / 86_400_000)}d ago`;
	}
</script>

<SEOHead title="Simulation runs" />

<div class="mx-auto max-w-5xl space-y-6 p-6">
	<header>
		<h1 class="text-2xl font-semibold">Simulation runs</h1>
		<p class="text-sm text-muted-foreground">
			Spawn new what-if runs of the HP Metal Jet S100 digital twin. Click any run to scrub its
			playback.
		</p>
	</header>

	<!-- Start form -->
	<section class="space-y-3 rounded-lg border bg-card p-4">
		<h2 class="text-sm font-semibold">Start a new run</h2>
		<div class="grid gap-3 md:grid-cols-3">
			<label class="space-y-1 text-sm">
				<span class="text-muted-foreground">Scenario</span>
				<select
					class="block w-full rounded-md border bg-background px-2 py-1.5 text-sm"
					bind:value={scenario}
					disabled={busy}
				>
					{#each SCENARIOS as s (s)}
						<option value={s}>{s}</option>
					{/each}
				</select>
			</label>

			<label class="space-y-1 text-sm">
				<span class="text-muted-foreground">Seed <span class="text-xs">(optional)</span></span>
				<input
					type="number"
					class="block w-full rounded-md border bg-background px-2 py-1.5 text-sm"
					placeholder="(scenario default)"
					bind:value={seed}
					disabled={busy}
				/>
			</label>

			<label class="space-y-1 text-sm">
				<span class="text-muted-foreground"
					>Horizon ticks <span class="text-xs">(optional)</span></span
				>
				<input
					type="number"
					min="1"
					max="10000"
					class="block w-full rounded-md border bg-background px-2 py-1.5 text-sm"
					placeholder="(scenario default)"
					bind:value={horizonTicks}
					disabled={busy}
				/>
			</label>
		</div>

		<div class="flex items-center gap-3 pt-1">
			<button
				type="button"
				class="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
				onclick={startRun}
				disabled={busy}
			>
				{busy ? 'Running…' : 'Run scenario'}
			</button>

			{#if errorMessage}
				<span class="text-sm text-destructive">{errorMessage}</span>
			{/if}
		</div>
	</section>

	<!-- Runs list -->
	<section>
		<h2 class="mb-2 text-sm font-semibold">Your runs</h2>
		{#if runsQuery.isLoading}
			<div class="text-sm text-muted-foreground">Loading…</div>
		{:else if !runsQuery.data || runsQuery.data.length === 0}
			<div class="rounded-lg border bg-card p-4 text-sm text-muted-foreground">
				No runs yet. Start one above.
			</div>
		{:else}
			<ul class="divide-y rounded-lg border bg-card">
				{#each runsQuery.data as run (run._id)}
					<li>
						<a
							href={resolve(localizedHref(`/app/runs/${run._id}`))}
							class="flex flex-wrap items-baseline justify-between gap-3 px-4 py-3 text-sm hover:bg-accent"
						>
							<span class="flex items-baseline gap-3">
								<span class={`h-2 w-2 rounded-full ${statusColor(run.status)}`}></span>
								<span class="font-medium">{run.scenarioName}</span>
								<code class="font-mono text-xs text-muted-foreground">{run._id}</code>
							</span>
							<span class="font-mono text-xs text-muted-foreground tabular-nums">
								tick {run.lastTick ?? 0}/{run.horizonTicks} · {fmtRelative(run.startedAt)}
							</span>
						</a>
					</li>
				{/each}
			</ul>
		{/if}
	</section>
</div>
