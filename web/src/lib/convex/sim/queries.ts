/**
 * Read queries for the printer simulation historian.
 *
 * Two flavors per logical query, both backed by the same `_*` helper so
 * the ownership/shape contract stays in one place:
 *   - `authedQuery` for direct client `useQuery` calls — derives userId from
 *     Better Auth via `ctx.user`.
 *   - `internalQuery` taking `userId` as an arg — for the agent's createTool
 *     handlers, which receive the user identity via `ToolCtx.userId` (set by
 *     `aiChatAgent.createThread({ userId })`). Auth identity does NOT cross
 *     `ctx.runQuery` boundaries, so the agent path must pass userId explicitly.
 *
 * All payloads include `runId`/`tick`/`componentId` so the agent can cite a
 * specific data point per the Phase 3 grounding protocol.
 */
import { ConvexError, v } from 'convex/values';
import { authedQuery } from '../functions';
import { internalQuery } from '../_generated/server';
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

// ---------- shared handlers ----------

async function _listMyRuns(ctx: QueryCtx, userId: string, limit: number) {
	const cap = Math.min(limit, 200);
	return await ctx.db
		.query('simRuns')
		.withIndex('by_user', (q) => q.eq('userId', userId))
		.order('desc')
		.take(cap);
}

async function _getRun(ctx: QueryCtx, userId: string, runId: Id<'simRuns'>) {
	return await assertOwnership(ctx, runId, userId);
}

async function _getRunSummary(ctx: QueryCtx, userId: string, runId: Id<'simRuns'>) {
	const run = await assertOwnership(ctx, runId, userId);
	return {
		runId: run._id,
		scenarioName: run.scenarioName,
		seed: run.seed,
		horizonTicks: run.horizonTicks,
		status: run.status,
		startedAt: run.startedAt,
		completedAt: run.completedAt ?? null,
		lastTick: run.lastTick ?? null,
		errorMessage: run.errorMessage ?? null,
		// Resolved scenario YAML (climate / drivers / maintenance) — JSON
		// string so consumers parse it themselves. Null on runs predating the
		// recordRunConfig wiring.
		scenarioConfig: run.scenarioConfig ?? null
	};
}

async function _getStateAtTick(ctx: QueryCtx, userId: string, runId: Id<'simRuns'>, tick: number) {
	await assertOwnership(ctx, runId, userId);

	const tickRow = await ctx.db
		.query('simTicks')
		.withIndex('by_run_and_tick', (q) => q.eq('runId', runId).eq('tick', tick))
		.unique();
	if (!tickRow) return null;

	const components = await ctx.db
		.query('simComponents')
		.withIndex('by_run_tick_component', (q) => q.eq('runId', runId).eq('tick', tick))
		.collect();

	const observed = await ctx.db
		.query('simObservedComponents')
		.withIndex('by_run_tick_component', (q) => q.eq('runId', runId).eq('tick', tick))
		.collect();

	return {
		runId,
		tick,
		tsIso: tickRow.tsIso,
		drivers: tickRow.drivers,
		env: tickRow.env,
		couplingFactors: tickRow.couplingFactors,
		printOutcome: tickRow.printOutcome,
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

async function _getComponentTimeseries(
	ctx: QueryCtx,
	userId: string,
	runId: Id<'simRuns'>,
	component: typeof componentId.type,
	fromTick?: number,
	toTick?: number
) {
	await assertOwnership(ctx, runId, userId);

	// Bounded read: 6 components × <=10000 ticks (config-clamped).
	const all = await ctx.db
		.query('simComponents')
		.withIndex('by_run_tick_component', (q) => q.eq('runId', runId))
		.collect();

	const filtered = all
		.filter((row) => row.componentId === component)
		.filter((row) => (fromTick === undefined ? true : row.tick >= fromTick))
		.filter((row) => (toTick === undefined ? true : row.tick <= toTick))
		.sort((a, b) => a.tick - b.tick);

	return filtered.map((row) => ({
		runId,
		tick: row.tick,
		componentId: row.componentId,
		healthIndex: row.healthIndex,
		status: row.status,
		ageTicks: row.ageTicks,
		metrics: row.metrics
	}));
}

async function _getDriversTimeseries(
	ctx: QueryCtx,
	userId: string,
	runId: Id<'simRuns'>,
	fromTick?: number,
	toTick?: number
) {
	await assertOwnership(ctx, runId, userId);

	// Bounded read: one row per tick, capped server-side at run.horizonTicks
	// (typically <= 1500 weekly ticks per the latest sim contract).
	const all = await ctx.db
		.query('simTicks')
		.withIndex('by_run_and_tick', (q) => q.eq('runId', runId))
		.collect();

	return all
		.filter((row) => (fromTick === undefined ? true : row.tick >= fromTick))
		.filter((row) => (toTick === undefined ? true : row.tick <= toTick))
		.sort((a, b) => a.tick - b.tick)
		.map((row) => ({
			runId,
			tick: row.tick,
			temperatureStress: row.drivers.temperatureStress,
			humidityContamination: row.drivers.humidityContamination,
			operationalLoad: row.drivers.operationalLoad,
			maintenanceLevel: row.drivers.maintenanceLevel,
			printOutcome: row.printOutcome
		}));
}

async function _getStatusTransitionsWithDrivers(
	ctx: QueryCtx,
	userId: string,
	runId: Id<'simRuns'>
) {
	await assertOwnership(ctx, runId, userId);

	// Walk the component-state stream once, find the first tick each
	// (componentId, status) appears. Server-side join with simTicks for
	// the dominant coupling factor at the transition tick — this powers
	// the dashboard's Proactive alerts feed without N+1 client queries.
	const componentRows = await ctx.db
		.query('simComponents')
		.withIndex('by_run_tick_component', (q) => q.eq('runId', runId))
		.collect();

	type FirstSeen = { componentId: string; status: string; firstTick: number };
	const firstByKey = new Map<string, FirstSeen>();
	for (const row of componentRows) {
		const key = `${row.componentId}:${row.status}`;
		const prev = firstByKey.get(key);
		if (prev === undefined || row.tick < prev.firstTick) {
			firstByKey.set(key, {
				componentId: row.componentId,
				status: row.status,
				firstTick: row.tick
			});
		}
	}

	const transitions = Array.from(firstByKey.values()).sort((a, b) => a.firstTick - b.firstTick);

	// Pull every needed tick row once and index by tick to avoid O(N) per-row reads.
	const neededTicks = new Set(transitions.map((t) => t.firstTick));
	const tickRows = await ctx.db
		.query('simTicks')
		.withIndex('by_run_and_tick', (q) => q.eq('runId', runId))
		.collect();
	const tickByTick = new Map(
		tickRows.filter((r) => neededTicks.has(r.tick)).map((r) => [r.tick, r])
	);

	return transitions.map((t) => {
		const tickRow = tickByTick.get(t.firstTick);
		const factors = tickRow?.couplingFactors ?? {};
		let topKey: string | null = null;
		let topAbs = -1;
		let topVal = 0;
		for (const [k, v] of Object.entries(factors)) {
			const abs = Math.abs(v);
			if (abs > topAbs) {
				topAbs = abs;
				topKey = k;
				topVal = v;
			}
		}
		return {
			runId,
			componentId: t.componentId,
			status: t.status,
			firstTick: t.firstTick,
			topDriverKey: topKey,
			topDriverValue: topKey === null ? null : topVal
		};
	});
}

async function _listEvents(
	ctx: QueryCtx,
	userId: string,
	runId: Id<'simRuns'>,
	fromTick?: number,
	toTick?: number,
	limit?: number
) {
	await assertOwnership(ctx, runId, userId);

	const cap = Math.min(limit ?? 100, 500);
	// Bounded: events per run are O(maintenance ticks), ~hundreds max.
	const events = await ctx.db
		.query('simEvents')
		.withIndex('by_run', (q) => q.eq('runId', runId))
		.collect();

	return events
		.filter((e) => (fromTick === undefined ? true : e.tick >= fromTick))
		.filter((e) => (toTick === undefined ? true : e.tick <= toTick))
		.sort((a, b) => a.tick - b.tick)
		.slice(0, cap)
		.map((e) => ({
			runId,
			tick: e.tick,
			kind: e.kind,
			componentId: e.componentId ?? null,
			tsIso: e.tsIso,
			payload: e.payload
		}));
}

async function _inspectSensorTrust(
	ctx: QueryCtx,
	userId: string,
	runId: Id<'simRuns'>,
	component: typeof componentId.type,
	fromTick?: number,
	toTick?: number
) {
	await assertOwnership(ctx, runId, userId);

	const trueRows = await ctx.db
		.query('simComponents')
		.withIndex('by_run_tick_component', (q) => q.eq('runId', runId))
		.collect();
	const obsRows = await ctx.db
		.query('simObservedComponents')
		.withIndex('by_run_tick_component', (q) => q.eq('runId', runId))
		.collect();

	const obsByTick = new Map(
		obsRows.filter((r) => r.componentId === component).map((r) => [r.tick, r])
	);

	const filtered = trueRows
		.filter((r) => r.componentId === component)
		.filter((r) => (fromTick === undefined ? true : r.tick >= fromTick))
		.filter((r) => (toTick === undefined ? true : r.tick <= toTick))
		.sort((a, b) => a.tick - b.tick);

	return filtered.map((row) => {
		const obs = obsByTick.get(row.tick);
		const observedHealth = obs?.observedHealthIndex ?? null;
		const gap = observedHealth === null ? null : row.healthIndex - observedHealth;
		return {
			runId,
			tick: row.tick,
			componentId: row.componentId,
			trueHealthIndex: row.healthIndex,
			observedHealthIndex: observedHealth,
			gap,
			sensorNote: obs?.sensorNote ?? null
		};
	});
}

async function _compareRuns(
	ctx: QueryCtx,
	userId: string,
	runIdA: Id<'simRuns'>,
	runIdB: Id<'simRuns'>,
	component: typeof componentId.type
) {
	await assertOwnership(ctx, runIdA, userId);
	await assertOwnership(ctx, runIdB, userId);

	async function lastHealth(rid: Id<'simRuns'>) {
		const rows = await ctx.db
			.query('simComponents')
			.withIndex('by_run_tick_component', (q) => q.eq('runId', rid))
			.collect();
		const filtered = rows
			.filter((r) => r.componentId === component)
			.sort((a, b) => b.tick - a.tick);
		return filtered[0] ?? null;
	}

	const [a, b] = await Promise.all([lastHealth(runIdA), lastHealth(runIdB)]);
	return {
		componentId: component,
		a: a ? { runId: runIdA, tick: a.tick, healthIndex: a.healthIndex, status: a.status } : null,
		b: b ? { runId: runIdB, tick: b.tick, healthIndex: b.healthIndex, status: b.status } : null
	};
}

// ---------- public (frontend useQuery) ----------

export const listMyRuns = authedQuery({
	args: { limit: v.optional(v.number()) },
	handler: async (ctx, args) => _listMyRuns(ctx, ctx.user._id, args.limit ?? 50)
});

export const getRun = authedQuery({
	args: { runId: v.id('simRuns') },
	handler: async (ctx, args) => _getRun(ctx, ctx.user._id, args.runId)
});

export const getRunSummary = authedQuery({
	args: { runId: v.id('simRuns') },
	handler: async (ctx, args) => _getRunSummary(ctx, ctx.user._id, args.runId)
});

export const getStateAtTick = authedQuery({
	args: { runId: v.id('simRuns'), tick: v.number() },
	handler: async (ctx, args) => _getStateAtTick(ctx, ctx.user._id, args.runId, args.tick)
});

export const getComponentTimeseries = authedQuery({
	args: {
		runId: v.id('simRuns'),
		componentId,
		fromTick: v.optional(v.number()),
		toTick: v.optional(v.number())
	},
	handler: async (ctx, args) =>
		_getComponentTimeseries(
			ctx,
			ctx.user._id,
			args.runId,
			args.componentId,
			args.fromTick,
			args.toTick
		)
});

export const listEvents = authedQuery({
	args: {
		runId: v.id('simRuns'),
		fromTick: v.optional(v.number()),
		toTick: v.optional(v.number()),
		limit: v.optional(v.number())
	},
	handler: async (ctx, args) =>
		_listEvents(ctx, ctx.user._id, args.runId, args.fromTick, args.toTick, args.limit)
});

export const inspectSensorTrust = authedQuery({
	args: {
		runId: v.id('simRuns'),
		componentId,
		fromTick: v.optional(v.number()),
		toTick: v.optional(v.number())
	},
	handler: async (ctx, args) =>
		_inspectSensorTrust(ctx, ctx.user._id, args.runId, args.componentId, args.fromTick, args.toTick)
});

export const getDriversTimeseries = authedQuery({
	args: {
		runId: v.id('simRuns'),
		fromTick: v.optional(v.number()),
		toTick: v.optional(v.number())
	},
	handler: async (ctx, args) =>
		_getDriversTimeseries(ctx, ctx.user._id, args.runId, args.fromTick, args.toTick)
});

export const getStatusTransitionsWithDrivers = authedQuery({
	args: { runId: v.id('simRuns') },
	handler: async (ctx, args) => _getStatusTransitionsWithDrivers(ctx, ctx.user._id, args.runId)
});

export const compareRuns = authedQuery({
	args: {
		runIdA: v.id('simRuns'),
		runIdB: v.id('simRuns'),
		componentId
	},
	handler: async (ctx, args) =>
		_compareRuns(ctx, ctx.user._id, args.runIdA, args.runIdB, args.componentId)
});

// ---------- internal (agent createTool, ToolCtx.userId) ----------

export const listMyRunsForUser = internalQuery({
	args: { userId: v.string(), limit: v.optional(v.number()) },
	handler: async (ctx, args) => _listMyRuns(ctx, args.userId, args.limit ?? 50)
});

export const getRunForUser = internalQuery({
	args: { userId: v.string(), runId: v.id('simRuns') },
	handler: async (ctx, args) => _getRun(ctx, args.userId, args.runId)
});

export const getRunSummaryForUser = internalQuery({
	args: { userId: v.string(), runId: v.id('simRuns') },
	handler: async (ctx, args) => _getRunSummary(ctx, args.userId, args.runId)
});

export const getStateAtTickForUser = internalQuery({
	args: { userId: v.string(), runId: v.id('simRuns'), tick: v.number() },
	handler: async (ctx, args) => _getStateAtTick(ctx, args.userId, args.runId, args.tick)
});

export const getComponentTimeseriesForUser = internalQuery({
	args: {
		userId: v.string(),
		runId: v.id('simRuns'),
		componentId,
		fromTick: v.optional(v.number()),
		toTick: v.optional(v.number())
	},
	handler: async (ctx, args) =>
		_getComponentTimeseries(
			ctx,
			args.userId,
			args.runId,
			args.componentId,
			args.fromTick,
			args.toTick
		)
});

export const listEventsForUser = internalQuery({
	args: {
		userId: v.string(),
		runId: v.id('simRuns'),
		fromTick: v.optional(v.number()),
		toTick: v.optional(v.number()),
		limit: v.optional(v.number())
	},
	handler: async (ctx, args) =>
		_listEvents(ctx, args.userId, args.runId, args.fromTick, args.toTick, args.limit)
});

export const inspectSensorTrustForUser = internalQuery({
	args: {
		userId: v.string(),
		runId: v.id('simRuns'),
		componentId,
		fromTick: v.optional(v.number()),
		toTick: v.optional(v.number())
	},
	handler: async (ctx, args) =>
		_inspectSensorTrust(ctx, args.userId, args.runId, args.componentId, args.fromTick, args.toTick)
});

export const getDriversTimeseriesForUser = internalQuery({
	args: {
		userId: v.string(),
		runId: v.id('simRuns'),
		fromTick: v.optional(v.number()),
		toTick: v.optional(v.number())
	},
	handler: async (ctx, args) =>
		_getDriversTimeseries(ctx, args.userId, args.runId, args.fromTick, args.toTick)
});

export const getStatusTransitionsWithDriversForUser = internalQuery({
	args: { userId: v.string(), runId: v.id('simRuns') },
	handler: async (ctx, args) => _getStatusTransitionsWithDrivers(ctx, args.userId, args.runId)
});

export const compareRunsForUser = internalQuery({
	args: {
		userId: v.string(),
		runIdA: v.id('simRuns'),
		runIdB: v.id('simRuns'),
		componentId
	},
	handler: async (ctx, args) =>
		_compareRuns(ctx, args.userId, args.runIdA, args.runIdB, args.componentId)
});
// TEST 1777174776
