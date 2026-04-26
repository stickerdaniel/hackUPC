<script lang="ts">
	import { useQuery } from 'convex-svelte';
	import { api } from '$lib/convex/_generated/api';
	import type { Id } from '$lib/convex/_generated/dataModel';

	const { runId = null }: { runId?: Id<'simRuns'> | null } = $props();

	// ──────────────────────────────────────────────────────────────────────
	// Constants — palette + per-component cascade-chain templates.
	// Mirrors sim/.../streamlit_app.py CASCADE_CHAINS so the two surfaces
	// tell the same story per failure.
	// ──────────────────────────────────────────────────────────────────────
	const ACCENT = '#024ad8';

	type ComponentId = 'blade' | 'rail' | 'nozzle' | 'cleaning' | 'heater' | 'sensor';
	type AlertStatus = 'DEGRADED' | 'CRITICAL' | 'FAILED';

	const CASCADE_CHAINS: Record<ComponentId, { requires: readonly string[]; template: string }> = {
		heater: {
			requires: ['sensor_bias_c', 'control_temp_error_c', 'heater_drift_frac'],
			template: 'sensor_bias ↑ → control_temp_error ↑ → heater_drift ↑ → HEATER'
		},
		nozzle: {
			requires: ['humidity_contamination_effective', 'powder_spread_quality', 'nozzle_clog_pct'],
			template: 'humidity ↑ + powder_spread_quality ↓ → nozzle_clog ↑ → NOZZLE'
		},
		blade: {
			requires: ['rail_alignment_error', 'blade_loss_frac'],
			template: 'rail_alignment ↑ → blade.k_eff ↑ → blade_loss ↑ → BLADE'
		},
		rail: {
			requires: ['blade_loss_frac', 'rail_alignment_error'],
			template: 'vibration ↑ + blade_loss ↑ → rail_alignment ↑ → RAIL'
		},
		cleaning: {
			requires: ['nozzle_clog_pct', 'cleaning_efficiency'],
			template: 'nozzle_clog ↑ → cleaning_wear ↑ → cleaning_efficiency ↓ → CLEANING'
		},
		sensor: {
			requires: ['temperature_stress_effective', 'heater_drift_frac', 'sensor_bias_c'],
			template: 'temperature_stress ↑ + heater_drift ↑ → sensor_bias ↑ → SENSOR'
		}
	};

	const ACTION_RULES: Record<AlertStatus, { verb: string; tip: string }> = {
		DEGRADED: { verb: 'WATCH', tip: 'Watch closely — schedule preventive in next window' },
		CRITICAL: {
			verb: 'SCHEDULE FIX',
			tip: 'Schedule a FIX in the next maintenance window'
		},
		FAILED: {
			verb: 'REPLACE NOW',
			tip: 'Replace immediately — print outcomes are degrading'
		}
	};

	type RecCard = {
		component: ComponentId;
		firstTick: number;
		status: AlertStatus;
		health: number | null;
		topDriverKey: string;
		topDriverValue: number;
		chain: string | null;
	};

	// ──────────────────────────────────────────────────────────────────────
	// Synthetic placeholder — same shape as the real cards so the block
	// renders sensibly without a run selected (marketing/demo path).
	// ──────────────────────────────────────────────────────────────────────
	const SYNTHETIC_CARDS: RecCard[] = [
		{
			component: 'nozzle',
			firstTick: 11,
			status: 'FAILED',
			health: 0.17,
			topDriverKey: 'powder_spread_quality',
			topDriverValue: 0.865,
			chain: 'humidity ↑ + powder_spread_quality ↓ → nozzle_clog ↑ → NOZZLE FAILED'
		},
		{
			component: 'cleaning',
			firstTick: 109,
			status: 'FAILED',
			health: 0.19,
			topDriverKey: 'powder_spread_quality',
			topDriverValue: 0.782,
			chain: 'nozzle_clog ↑ → cleaning_wear ↑ → cleaning_efficiency ↓ → CLEANING FAILED'
		},
		{
			component: 'rail',
			firstTick: 58,
			status: 'FAILED',
			health: 0.19,
			topDriverKey: 'cleaning_efficiency',
			topDriverValue: 0.853,
			chain: 'vibration ↑ + blade_loss ↑ → rail_alignment ↑ → RAIL FAILED'
		},
		{
			component: 'heater',
			firstTick: 62,
			status: 'FAILED',
			health: 0.2,
			topDriverKey: 'powder_spread_quality',
			topDriverValue: 0.948,
			chain: null
		},
		{
			component: 'blade',
			firstTick: 58,
			status: 'FAILED',
			health: 0.2,
			topDriverKey: 'cleaning_efficiency',
			topDriverValue: 0.853,
			chain: 'rail_alignment ↑ → blade.k_eff ↑ → blade_loss ↑ → BLADE FAILED'
		}
	];

	// ──────────────────────────────────────────────────────────────────────
	// Real data — transitions + per-component health timeseries.
	// Convex deduplicates so the per-component queries here piggyback on
	// the ones already issued by HealthTimeline + DriverCoupledDecay.
	// ──────────────────────────────────────────────────────────────────────
	const transitionsQuery = useQuery(api.sim.queries.getStatusTransitionsWithDrivers, () =>
		runId ? { runId } : 'skip'
	);

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

	type CmpRow = { tick: number; healthIndex: number };
	function lookupHealth(rows: CmpRow[] | undefined, tick: number): number | null {
		if (!rows || rows.length === 0) return null;
		const exact = rows.find((r) => r.tick === tick);
		if (exact) return exact.healthIndex;
		// Fallback: nearest-tick (covers ticks slightly off due to downsampling).
		let best: CmpRow | null = null;
		let bestDist = Infinity;
		for (const r of rows) {
			const d = Math.abs(r.tick - tick);
			if (d < bestDist) {
				bestDist = d;
				best = r;
			}
		}
		return best ? best.healthIndex : null;
	}

	const realCards = $derived.by((): RecCard[] | null => {
		const rows = transitionsQuery.data;
		if (!runId || !rows || rows.length === 0) return null;
		const healthBy: Record<ComponentId, CmpRow[] | undefined> = {
			blade: cmpBladeQ.data,
			rail: cmpRailQ.data,
			nozzle: cmpNozzleQ.data,
			cleaning: cmpCleaningQ.data,
			heater: cmpHeaterQ.data,
			sensor: cmpSensorQ.data
		};

		// One card per (componentId, worstStatus reached) — pick FAILED if
		// reached, else CRITICAL, else DEGRADED. Sort worst-first then earliest.
		const allowed = new Set<AlertStatus>(['DEGRADED', 'CRITICAL', 'FAILED']);
		const rank = (s: AlertStatus): number => (s === 'FAILED' ? 3 : s === 'CRITICAL' ? 2 : 1);
		// Plain object (not Map) keeps svelte/prefer-svelte-reactivity happy —
		// this is a transient lookup, never assigned to component state.
		const byComponent: Partial<Record<ComponentId, RecCard>> = {};
		for (const row of rows) {
			if (!allowed.has(row.status as AlertStatus)) continue;
			const cid = row.componentId as ComponentId;
			const status = row.status as AlertStatus;
			const existing = byComponent[cid];
			if (existing && rank(status) <= rank(existing.status)) continue;

			const tickRows = healthBy[cid];
			const health = lookupHealth(tickRows, row.firstTick);

			const tmpl = CASCADE_CHAINS[cid];
			let chain: string | null = null;
			if (tmpl && row.topDriverKey && tmpl.requires.includes(row.topDriverKey)) {
				chain = `${tmpl.template} ${status}`;
			}

			byComponent[cid] = {
				component: cid,
				firstTick: row.firstTick,
				status,
				health,
				topDriverKey: row.topDriverKey ?? '—',
				topDriverValue: row.topDriverValue ?? 0,
				chain
			};
		}

		const ordered = (Object.values(byComponent) as RecCard[]).sort((a, b) => {
			// Display order: worst-first (FAILED before CRITICAL before DEGRADED).
			const displayRank = (s: AlertStatus): number =>
				s === 'FAILED' ? 0 : s === 'CRITICAL' ? 1 : 2;
			const r = displayRank(a.status) - displayRank(b.status);
			if (r !== 0) return r;
			return a.firstTick - b.firstTick;
		});
		return ordered;
	});

	const cards = $derived(realCards ?? SYNTHETIC_CARDS);

	function fmtFactor(v: number): string {
		return v.toFixed(3);
	}
	function fmtHealth(h: number | null): string {
		return h === null ? '—' : h.toFixed(2);
	}
</script>

<section class="rec">
	<header class="rec-head">
		<div class="rec-eyebrow-top">Phase 3 preview · Reliability · Intelligence · Autonomy</div>
		<div class="rec-eyebrow">Phase 3 / Heuristic preview</div>
		<h2 class="rec-title">Recommendation cards</h2>
		<p class="rec-sub">
			Read-only insight cards — rule-based today (status → suggested action lookup).
		</p>
	</header>

	{#if cards.length === 0}
		<div class="rec-empty">No DEGRADED/CRITICAL/FAILED transitions in this run.</div>
	{/if}

	<div class="rec-stack">
		{#each cards as card (card.component + ':' + card.status)}
			{@const action = ACTION_RULES[card.status]}
			<article class="rec-card">
				<header class="rec-card-head">
					<span class="rec-dot" style:background={ACCENT}></span>
					<span class="rec-component">{card.component.toUpperCase()}</span>
					<span class="rec-meta">
						<span class="rec-meta-key">@</span>
						<span class="mono">T={card.firstTick}</span>
						<span class="rec-meta-sep">·</span>
						<span class="rec-meta-key">HEALTH</span>
						<span class="mono">{fmtHealth(card.health)}</span>
						<span class="rec-meta-sep">·</span>
						<span class="rec-meta-key">STATUS</span>
						<span class="mono">{card.status}</span>
					</span>
				</header>

				<div class="rec-why">
					<span class="rec-why-key">Why:</span>
					top driver was
					<code class="rec-codepill mono">
						{card.topDriverKey} = {fmtFactor(card.topDriverValue)}
					</code>
					{#if card.chain}
						. <span class="rec-chain">{card.chain}</span>
					{:else}
						. <span class="rec-chain rec-chain-faded">
							Cascade chain not recoverable from the recorded factors.
						</span>
					{/if}
				</div>

				<footer class="rec-foot">
					<span class="rec-foot-key">SUGGESTED NEXT STEP</span>
					<span class="rec-action">
						<span class="rec-action-dot" style:background={ACCENT}></span>
						{action.verb}
					</span>
					<span class="rec-foot-tip">· {action.tip}</span>
				</footer>
			</article>
		{/each}
	</div>
</section>

<style>
	.rec {
		--accent: #024ad8;
		--fg: #000000;
		--fg-3: #5a5a5a;
		--fg-4: #8a8a8a;
		--line: #e6e6e6;
		--surface: #ffffff;
		--codebg: #f4f6ff;
		--sans: 'Wix Madefor Text', 'HP Simplified', 'Helvetica Neue', Helvetica, Arial, sans-serif;
		--display:
			'Wix Madefor Display', 'HP Simplified', 'Helvetica Neue', Helvetica, Arial, sans-serif;

		max-width: 1280px;
		margin: 0 auto;
		padding: 32px 40px 56px;
		font-family: var(--sans);
		color: var(--fg);
		border-top: 1px solid var(--line);
	}

	.mono {
		font-feature-settings:
			'tnum' 1,
			'zero' 1;
	}

	/* ─── Header ─── */
	.rec-head {
		margin-bottom: 24px;
	}
	.rec-eyebrow-top {
		font-size: 11px;
		font-weight: 700;
		letter-spacing: 0.16em;
		color: var(--accent);
		text-transform: uppercase;
		margin-bottom: 28px;
	}
	.rec-eyebrow {
		font-size: 11px;
		font-weight: 700;
		letter-spacing: 0.16em;
		color: var(--accent);
		text-transform: uppercase;
		margin-bottom: 4px;
	}
	.rec-title {
		font-family: var(--display);
		font-size: clamp(22px, 2.4vw, 30px);
		font-weight: 800;
		letter-spacing: -0.025em;
		margin: 0 0 8px;
		color: var(--fg);
	}
	.rec-sub {
		margin: 0;
		font-size: 13px;
		line-height: 1.5;
		color: var(--fg-3);
		max-width: 78ch;
	}

	/* ─── Stack of cards ─── */
	.rec-stack {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.rec-empty {
		font-size: 13px;
		color: var(--fg-4);
		font-style: italic;
		padding: 20px;
		border: 1px dashed var(--line);
		border-radius: 10px;
		text-align: center;
	}

	/* ─── Single card ─── */
	.rec-card {
		border: 1px solid var(--line);
		border-radius: 10px;
		padding: 16px 20px;
		background: var(--surface);
		transition: border-color 120ms;
	}
	.rec-card:hover {
		border-color: #cfd5d8;
	}

	.rec-card-head {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
		margin-bottom: 10px;
	}
	.rec-dot {
		width: 10px;
		height: 10px;
		border-radius: 999px;
		flex-shrink: 0;
	}
	.rec-component {
		font-family: var(--display);
		font-weight: 800;
		font-size: 14px;
		letter-spacing: 0.04em;
		color: var(--fg);
	}
	.rec-meta {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 11px;
		color: var(--fg-4);
	}
	.rec-meta-key {
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
	}
	.rec-meta-sep {
		color: var(--fg-4);
	}

	/* ─── Why row ─── */
	.rec-why {
		font-size: 13.5px;
		line-height: 1.7;
		color: var(--fg);
		margin-bottom: 14px;
	}
	.rec-why-key {
		font-weight: 700;
		margin-right: 4px;
	}
	.rec-codepill {
		display: inline-block;
		padding: 2px 8px;
		background: var(--codebg);
		border-radius: 4px;
		font-size: 12.5px;
		color: var(--fg);
		font-family: ui-monospace, 'SF Mono', 'Menlo', 'Consolas', monospace;
	}
	.rec-chain {
		color: var(--fg);
	}
	.rec-chain-faded {
		color: var(--fg-3);
		font-style: italic;
	}

	/* ─── Footer / suggested next step ─── */
	.rec-foot {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
		font-size: 13px;
	}
	.rec-foot-key {
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.16em;
		color: var(--fg-3);
		text-transform: uppercase;
	}
	.rec-action {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 4px 12px;
		background: var(--surface);
		color: var(--accent);
		border: 1px solid var(--accent);
		border-radius: 6px;
		font-size: 12px;
		font-weight: 800;
		letter-spacing: 0.08em;
	}
	.rec-action-dot {
		width: 6px;
		height: 6px;
		border-radius: 999px;
	}
	.rec-foot-tip {
		color: var(--fg-3);
	}

	@media (max-width: 720px) {
		.rec {
			padding: 24px 16px 40px;
		}
		.rec-card {
			padding: 14px 14px;
		}
	}
</style>
