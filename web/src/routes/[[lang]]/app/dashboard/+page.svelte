<script lang="ts">
	import SEOHead from '$lib/components/SEOHead.svelte';
	import { getTranslate } from '@tolgee/svelte';
	import { useQuery } from 'convex-svelte';
	import { useSearchParams } from 'runed/kit';
	import * as v from 'valibot';
	import HealthTimeline from '$blocks/dashboard/health-timeline.svelte';
	import DriverCoupledDecay from '$blocks/dashboard/driver-coupled-decay.svelte';
	import RecommendationCards from '$blocks/dashboard/recommendation-cards.svelte';
	import { provideTimeWindow, TimeWindow } from '$lib/dashboard/time-window.svelte';
	import { api } from '$lib/convex/_generated/api';
	import type { Id } from '$lib/convex/_generated/dataModel';

	const { t } = getTranslate();

	// Shared across health-timeline + driver-coupled-decay so the time-window
	// pills in the lower block also drive the Component-health chart above.
	// Horizon updates reactively when a real run is selected.
	const DASHBOARD_HORIZON = 260;
	const tw = provideTimeWindow(new TimeWindow(DASHBOARD_HORIZON));

	// Run selection persisted in URL so deep-linking + reload keep state.
	const runParamSchema = v.object({
		run: v.optional(v.fallback(v.string(), ''), '')
	});
	const params = useSearchParams(runParamSchema, { pushHistory: true, noScroll: true });
	const selectedRunId = $derived(params.run ? (params.run as Id<'simRuns'>) : null);

	// Reactive list of runs for the picker dropdown.
	const runsQuery = useQuery(api.sim.queries.listMyRuns, () => ({ limit: 100 }));
	const runs = $derived(runsQuery.data ?? []);

	// Live summary of the selected run (skip when nothing picked).
	const summaryQuery = useQuery(api.sim.queries.getRunSummary, () =>
		selectedRunId ? { runId: selectedRunId } : 'skip'
	);
	const summary = $derived(summaryQuery.data);

	// Drive the shared TimeWindow from the actual run horizon so "all" shows
	// the full run instead of a 260-tick slice.
	$effect(() => {
		if (summary?.horizonTicks) tw.setHorizon(summary.horizonTicks);
	});

	function pickRun(e: Event) {
		const value = (e.currentTarget as HTMLSelectElement).value;
		params.run = value;
	}

	function clearRun() {
		params.run = '';
	}

	function fmtDate(iso: number | string | null | undefined): string {
		if (iso === null || iso === undefined) return '—';
		const ms = typeof iso === 'number' ? iso : Date.parse(iso);
		if (!Number.isFinite(ms)) return '—';
		const d = new Date(ms);
		return d.toLocaleDateString(undefined, { year: '2-digit', month: '2-digit', day: '2-digit' });
	}
</script>

<SEOHead
	title={$t('meta.app.dashboard.title')}
	description={$t('meta.app.dashboard.description')}
/>

<div class="dashboard-page">
	<header class="dash-intro">
		<div class="dash-intro-eyebrow mono">
			<span class="dash-intro-domain">HPCT.WORK</span>
			<span class="dash-intro-sep">·</span>
			<span class="dash-intro-product">HP METAL JET S100 DIGITAL TWIN</span>
		</div>

		<div class="dash-intro-titlerow">
			<h1 class="dash-intro-title">
				HP <span class="dash-intro-title-accent">CoPilot</span>
				<span class="dash-intro-title-soft">Twin</span>
			</h1>
			<span class="dash-intro-role">
				<span class="dash-intro-role-dot"></span>
				OPERATOR
			</span>
		</div>

		<p class="dash-intro-desc">
			Operator dashboard for the coupled simulation engine — drivers, status decay, cascade
			attribution, sensor trust, and operator response, sourced from the SQLite historian for the
			selected run.
		</p>

		<!-- Run picker — drives every chart on the page. -->
		<div class="dash-runpicker">
			<label class="dash-runpicker-label" for="dash-run-select">RUN</label>
			<div class="dash-runpicker-control">
				<select
					id="dash-run-select"
					class="dash-runpicker-select mono"
					value={selectedRunId ?? ''}
					onchange={pickRun}
				>
					<option value="">— Pick a run to load real data —</option>
					{#each runs as r (r._id)}
						<option value={r._id}>
							{r.scenarioName} · seed {r.seed} · {r.horizonTicks ?? '?'} ticks · {r.status}
						</option>
					{/each}
				</select>
				{#if selectedRunId}
					<button type="button" class="dash-runpicker-clear" onclick={clearRun}> Clear </button>
				{/if}
			</div>
			<div class="dash-runpicker-hint">
				{#if !selectedRunId}
					Charts below show synthetic placeholder data. Pick a run to render the real historian
					data.
				{:else if !summary}
					Loading run summary…
				{:else}
					Loaded <span class="mono">{summary.scenarioName}</span> · status
					<span class="mono">{summary.status}</span>
					{#if summary.lastTick !== null}· last tick <span class="mono">{summary.lastTick}</span
						>{/if}
				{/if}
			</div>
		</div>

		<div class="dash-intro-pills">
			{#if !selectedRunId}
				<span class="dash-pill dash-pill-empty">
					<span class="dash-pill-label">RUN</span>
					<span class="dash-pill-val mono">— no run selected —</span>
				</span>
			{:else if summary}
				<span class="dash-pill">
					<span class="dash-pill-label">RUN</span>
					<span class="dash-pill-val mono">{summary.runId}</span>
				</span>
				<span class="dash-pill">
					<span class="dash-pill-label">SCENARIO</span>
					<span class="dash-pill-val">{summary.scenarioName}</span>
				</span>
				<span class="dash-pill">
					<span class="dash-pill-label">SEED</span>
					<span class="dash-pill-val mono">{summary.seed}</span>
				</span>
				<span class="dash-pill">
					<span class="dash-pill-label">HORIZON</span>
					<span class="dash-pill-val mono">{summary.horizonTicks ?? '—'}</span>
				</span>
				<span class="dash-pill">
					<span class="dash-pill-label">STATUS</span>
					<span class="dash-pill-val mono">{summary.status}</span>
				</span>
				<span class="dash-pill">
					<span class="dash-pill-label">STARTED</span>
					<span class="dash-pill-val mono">{fmtDate(summary.startedAt)}</span>
				</span>
				{#if summary.completedAt !== null}
					<span class="dash-pill">
						<span class="dash-pill-label">COMPLETED</span>
						<span class="dash-pill-val mono">{fmtDate(summary.completedAt)}</span>
					</span>
				{/if}
				{#if summary.lastTick !== null}
					<span class="dash-pill">
						<span class="dash-pill-label">LAST TICK</span>
						<span class="dash-pill-val mono">{summary.lastTick}</span>
					</span>
				{/if}
			{/if}
		</div>
	</header>

	<HealthTimeline runId={selectedRunId} />
	<DriverCoupledDecay runId={selectedRunId} />
	<RecommendationCards runId={selectedRunId} />
</div>

<style>
	.dashboard-page {
		min-height: 100%;
		background: #ffffff;
		--accent: #024ad8;
		--fg: #000000;
		--fg-3: #5a5a5a;
		--fg-4: #8a8a8a;
		--line: #e6e6e6;
		--sans: 'Wix Madefor Text', 'HP Simplified', 'Helvetica Neue', Helvetica, Arial, sans-serif;
		--display:
			'Wix Madefor Display', 'HP Simplified', 'Helvetica Neue', Helvetica, Arial, sans-serif;
	}

	.dash-intro {
		max-width: 1280px;
		margin: 0 auto;
		padding: 48px 40px 24px;
		font-family: var(--sans);
		color: var(--fg);
	}

	.mono {
		font-feature-settings:
			'tnum' 1,
			'zero' 1;
		letter-spacing: 0.02em;
	}

	.dash-intro-eyebrow {
		display: inline-flex;
		align-items: center;
		gap: 12px;
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.18em;
		text-transform: uppercase;
		margin-bottom: 28px;
	}
	.dash-intro-domain {
		color: var(--accent);
	}
	.dash-intro-sep {
		color: var(--fg-4);
	}
	.dash-intro-product {
		color: var(--fg-3);
	}

	.dash-intro-titlerow {
		display: flex;
		align-items: center;
		gap: 24px;
		flex-wrap: wrap;
	}
	.dash-intro-title {
		font-family: var(--display);
		font-size: clamp(26px, 2.6vw, 36px);
		font-weight: 800;
		letter-spacing: -0.03em;
		line-height: 1;
		margin: 0;
		color: var(--fg);
	}
	.dash-intro-title-accent {
		color: var(--accent);
	}
	.dash-intro-title-soft {
		color: var(--fg-3);
		font-weight: 700;
	}

	.dash-intro-role {
		display: inline-flex;
		align-items: center;
		gap: 10px;
		padding: 9px 18px;
		background: #0a0a0a;
		color: #ffffff;
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.16em;
		border-radius: 999px;
		text-transform: uppercase;
	}
	.dash-intro-role-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: #18a957;
		box-shadow: 0 0 0 3px rgba(24, 169, 87, 0.18);
	}

	.dash-intro-desc {
		margin: 22px 0 28px;
		font-size: 16px;
		line-height: 1.55;
		color: var(--fg-3);
		max-width: 1100px;
	}

	.dash-runpicker {
		display: flex;
		align-items: center;
		gap: 14px;
		flex-wrap: wrap;
		padding: 14px 0 18px;
		margin: 18px 0 4px;
		border-top: 1px solid var(--line);
	}
	.dash-runpicker-label {
		font-size: 11px;
		font-weight: 700;
		letter-spacing: 0.18em;
		color: var(--accent);
		text-transform: uppercase;
		flex-shrink: 0;
	}
	.dash-runpicker-control {
		display: inline-flex;
		align-items: stretch;
		gap: 8px;
		flex-shrink: 0;
	}
	.dash-runpicker-select {
		appearance: none;
		background: #ffffff;
		border: 1px solid #cfdcfa;
		border-radius: 8px;
		padding: 8px 32px 8px 12px;
		font-size: 12px;
		font-family: var(--sans);
		color: var(--fg);
		min-width: 360px;
		max-width: 540px;
		cursor: pointer;
		background-image:
			linear-gradient(45deg, transparent 50%, var(--accent) 50%),
			linear-gradient(135deg, var(--accent) 50%, transparent 50%);
		background-position:
			calc(100% - 16px) 50%,
			calc(100% - 11px) 50%;
		background-size:
			5px 5px,
			5px 5px;
		background-repeat: no-repeat;
	}
	.dash-runpicker-select:focus {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.dash-runpicker-clear {
		appearance: none;
		background: #ffffff;
		border: 1px solid var(--line);
		border-radius: 8px;
		padding: 8px 14px;
		font-size: 12px;
		font-weight: 600;
		font-family: var(--sans);
		color: var(--fg-3);
		cursor: pointer;
	}
	.dash-runpicker-clear:hover {
		background: #f5f5f5;
		color: var(--fg);
	}
	.dash-runpicker-hint {
		font-size: 12px;
		color: var(--fg-3);
		flex: 1;
		min-width: 220px;
	}

	.dash-intro-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.dash-pill-empty .dash-pill-val {
		color: var(--fg-4);
		font-style: italic;
	}
	.dash-pill {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 7px 16px;
		background: #eff5ff;
		border: 1px solid #cfdcfa;
		border-radius: 999px;
		font-size: 12px;
		line-height: 1;
		white-space: nowrap;
	}
	.dash-pill-label {
		color: var(--accent);
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.14em;
		text-transform: uppercase;
	}
	.dash-pill-val {
		color: var(--fg);
		font-weight: 500;
	}
	.dash-pill-val.mono {
		font-feature-settings:
			'tnum' 1,
			'zero' 1;
	}
	.dash-pill-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}
	.dash-pill-dot[data-sev='ok'] {
		background: #18a957;
	}
	.dash-pill-dot[data-sev='degraded'] {
		background: #f5a524;
	}
	.dash-pill-dot[data-sev='halted'] {
		background: #e5484d;
	}

	@media (max-width: 720px) {
		.dash-intro {
			padding: 32px 24px 16px;
		}
		.dash-intro-titlerow {
			gap: 14px;
		}
	}
</style>
