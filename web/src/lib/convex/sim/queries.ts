/**
 * Public read queries for the printer simulation historian.
 *
 * Every query enforces ownership against `simRuns.userId` so a user can only
 * inspect their own runs. The agent's `createTool` handlers also call these,
 * receiving the user identity through the ToolCtx.
 *
 * All payloads include `runId`/`tick`/`componentId` so the agent can cite a
 * specific data point per the Phase 3 grounding protocol.
 */
import { ConvexError, v } from 'convex/values';
import { authedQuery } from '../functions';
import type { Doc, Id } from '../_generated/dataModel';
import type { QueryCtx } from '../_generated/server';

const componentId = v.union(
	v.literal('blade'),
	v.literal('rail'),
	v.literal('nozzle'),
	v.literal('cleaning'),
	v.literal('heater'),
	v.literal('sensor')
);

async function assertOwnership(
	ctx: QueryCtx,
	runId: Id<'simRuns'>,
	userId: string
): Promise<Doc<'simRuns'>> {
	const run = await ctx.db.get(runId);
	if (!run) throw new ConvexError(`run not found: ${runId}`);
	if (run.userId !== userId) throw new ConvexError('Not authorized for this run');
	return run;
}

export const listMyRuns = authedQuery({
	args: { limit: v.optional(v.number()) },
	handler: async (ctx, args) => {
		const limit = Math.min(args.limit ?? 50, 200);
		const userId = ctx.user._id;
		return await ctx.db
			.query('simRuns')
			.withIndex('by_user', (q) => q.eq('userId', userId))
			.order('desc')
			.take(limit);
	}
});

export const getRun = authedQuery({
	args: { runId: v.id('simRuns') },
	handler: async (ctx, args) => {
		const userId = ctx.user._id;
		return await assertOwnership(ctx, args.runId, userId);
	}
});

export const getRunSummary = authedQuery({
	args: { runId: v.id('simRuns') },
	handler: async (ctx, args) => {
		const userId = ctx.user._id;
		const run = await assertOwnership(ctx, args.runId, userId);
		return {
			runId: run._id,
			scenarioName: run.scenarioName,
			seed: run.seed,
			horizonTicks: run.horizonTicks,
			status: run.status,
			startedAt: run.startedAt,
			completedAt: run.completedAt ?? null,
			lastTick: run.lastTick ?? null,
			errorMessage: run.errorMessage ?? null
		};
	}
});

export const getStateAtTick = authedQuery({
	args: { runId: v.id('simRuns'), tick: v.number() },
	handler: async (ctx, args) => {
		const userId = ctx.user._id;
		await assertOwnership(ctx, args.runId, userId);

		const tick = await ctx.db
			.query('simTicks')
			.withIndex('by_run_and_tick', (q) => q.eq('runId', args.runId).eq('tick', args.tick))
			.unique();
		if (!tick) return null;

		const components = await ctx.db
			.query('simComponents')
			.withIndex('by_run_tick_component', (q) => q.eq('runId', args.runId).eq('tick', args.tick))
			.collect();

		const observed = await ctx.db
			.query('simObservedComponents')
			.withIndex('by_run_tick_component', (q) => q.eq('runId', args.runId).eq('tick', args.tick))
			.collect();

		return {
			runId: args.runId,
			tick: args.tick,
			tsIso: tick.tsIso,
			drivers: tick.drivers,
			env: tick.env,
			couplingFactors: tick.couplingFactors,
			printOutcome: tick.printOutcome,
			components: components.map((c) => ({
				componentId: c.componentId,
				healthIndex: c.healthIndex,
				status: c.status,
				ageTicks: c.ageTicks,
				metrics: c.metrics
			})),
			observed: observed.map((o) => ({
				componentId: o.componentId,
				observedHealthIndex: o.observedHealthIndex ?? null,
				observedStatus: o.observedStatus ?? null,
				sensorNote: o.sensorNote,
				observedMetrics: o.observedMetrics,
				sensorHealth: o.sensorHealth
			}))
		};
	}
});

export const getComponentTimeseries = authedQuery({
	args: {
		runId: v.id('simRuns'),
		componentId,
		fromTick: v.optional(v.number()),
		toTick: v.optional(v.number())
	},
	handler: async (ctx, args) => {
		const userId = ctx.user._id;
		await assertOwnership(ctx, args.runId, userId);

		// Bounded read: timeseries rows for one component on one run.
		// 6 components × <=10000 ticks (config-clamped) keeps this safe.
		const all = await ctx.db
			.query('simComponents')
			.withIndex('by_run_tick_component', (q) => q.eq('runId', args.runId))
			.collect();

		const filtered = all
			.filter((row) => row.componentId === args.componentId)
			.filter((row) => (args.fromTick === undefined ? true : row.tick >= args.fromTick))
			.filter((row) => (args.toTick === undefined ? true : row.tick <= args.toTick))
			.sort((a, b) => a.tick - b.tick);

		return filtered.map((row) => ({
			runId: args.runId,
			tick: row.tick,
			componentId: row.componentId,
			healthIndex: row.healthIndex,
			status: row.status,
			ageTicks: row.ageTicks,
			metrics: row.metrics
		}));
	}
});

export const listEvents = authedQuery({
	args: {
		runId: v.id('simRuns'),
		fromTick: v.optional(v.number()),
		toTick: v.optional(v.number()),
		limit: v.optional(v.number())
	},
	handler: async (ctx, args) => {
		const userId = ctx.user._id;
		await assertOwnership(ctx, args.runId, userId);

		const limit = Math.min(args.limit ?? 100, 500);
		// Bounded: events per run are O(maintenance ticks), ~hundreds max.
		const events = await ctx.db
			.query('simEvents')
			.withIndex('by_run', (q) => q.eq('runId', args.runId))
			.collect();

		return events
			.filter((e) => (args.fromTick === undefined ? true : e.tick >= args.fromTick))
			.filter((e) => (args.toTick === undefined ? true : e.tick <= args.toTick))
			.sort((a, b) => a.tick - b.tick)
			.slice(0, limit)
			.map((e) => ({
				runId: args.runId,
				tick: e.tick,
				kind: e.kind,
				componentId: e.componentId ?? null,
				tsIso: e.tsIso,
				payload: e.payload
			}));
	}
});

export const inspectSensorTrust = authedQuery({
	args: {
		runId: v.id('simRuns'),
		componentId,
		fromTick: v.optional(v.number()),
		toTick: v.optional(v.number())
	},
	handler: async (ctx, args) => {
		const userId = ctx.user._id;
		await assertOwnership(ctx, args.runId, userId);

		const trueRows = await ctx.db
			.query('simComponents')
			.withIndex('by_run_tick_component', (q) => q.eq('runId', args.runId))
			.collect();
		const obsRows = await ctx.db
			.query('simObservedComponents')
			.withIndex('by_run_tick_component', (q) => q.eq('runId', args.runId))
			.collect();

		const obsByTick = new Map(
			obsRows.filter((r) => r.componentId === args.componentId).map((r) => [r.tick, r])
		);

		const filtered = trueRows
			.filter((r) => r.componentId === args.componentId)
			.filter((r) => (args.fromTick === undefined ? true : r.tick >= args.fromTick))
			.filter((r) => (args.toTick === undefined ? true : r.tick <= args.toTick))
			.sort((a, b) => a.tick - b.tick);

		return filtered.map((row) => {
			const obs = obsByTick.get(row.tick);
			const observedHealth = obs?.observedHealthIndex ?? null;
			const gap = observedHealth === null ? null : row.healthIndex - observedHealth;
			return {
				runId: args.runId,
				tick: row.tick,
				componentId: row.componentId,
				trueHealthIndex: row.healthIndex,
				observedHealthIndex: observedHealth,
				gap,
				sensorNote: obs?.sensorNote ?? null
			};
		});
	}
});

export const compareRuns = authedQuery({
	args: {
		runIdA: v.id('simRuns'),
		runIdB: v.id('simRuns'),
		componentId
	},
	handler: async (ctx, args) => {
		const userId = ctx.user._id;
		await assertOwnership(ctx, args.runIdA, userId);
		await assertOwnership(ctx, args.runIdB, userId);

		async function lastHealth(runId: Id<'simRuns'>) {
			const rows = await ctx.db
				.query('simComponents')
				.withIndex('by_run_tick_component', (q) => q.eq('runId', runId))
				.collect();
			const filtered = rows
				.filter((r) => r.componentId === args.componentId)
				.sort((a, b) => b.tick - a.tick);
			return filtered[0] ?? null;
		}

		const [a, b] = await Promise.all([lastHealth(args.runIdA), lastHealth(args.runIdB)]);
		return {
			componentId: args.componentId,
			a: a
				? { runId: args.runIdA, tick: a.tick, healthIndex: a.healthIndex, status: a.status }
				: null,
			b: b
				? { runId: args.runIdB, tick: b.tick, healthIndex: b.healthIndex, status: b.status }
				: null
		};
	}
});
