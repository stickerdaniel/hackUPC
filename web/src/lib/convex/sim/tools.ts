/**
 * Agent tools for the printer simulator.
 *
 * Use `createTool` from `@convex-dev/agent` (NOT plain `tool()` from `ai`)
 * because handlers need Convex action `ctx` (`ctx.runQuery`, `ctx.runAction`).
 *
 * Auth identity does NOT propagate across `ctx.runQuery` / `ctx.runAction`
 * boundaries. The agent runtime populates `ctx.userId` on the ToolCtx from the
 * thread's userId (see `aiChatAgent.createThread({ userId: ctx.user._id })` in
 * `aiChat/threads.ts`), and tools MUST pass that to the `*ForUser` internal
 * versions of queries/actions. Calling the public `authedQuery` versions from
 * here would throw `Unauthenticated` because they re-derive auth from ctx.
 *
 * Every read result includes `runId`/`tick`/`componentId` so the agent can
 * cite specific data points (Phase 3 grounding protocol — never answer
 * printer state from training).
 */
import { createTool } from '@convex-dev/agent';
import { ConvexError } from 'convex/values';
import { z } from 'zod';
import { internal } from '../_generated/api';
import type { Id } from '../_generated/dataModel';

const componentSchema = z.enum(['blade', 'rail', 'nozzle', 'cleaning', 'heater', 'sensor']);

function requireUserId(ctx: { userId?: string }): string {
	if (!ctx.userId) {
		throw new ConvexError(
			'Tool ctx is missing userId. Make sure the thread was created with userId.'
		);
	}
	return ctx.userId;
}

export const listMyRuns = createTool({
	description:
		"List the user's recent simulation runs (most recent first). Returns runId, " +
		'scenarioName, status, lastTick, startedAt for each. Use this when the user ' +
		'asks about "my last run" / "my latest barcelona run" / "the run I just did" — ' +
		'never ask the user for a runId you can look up here.',
	args: z.object({
		limit: z.number().int().positive().max(50).optional()
	}),
	handler: async (ctx, args): Promise<unknown> => {
		const userId = requireUserId(ctx);
		return await ctx.runQuery(internal.sim.queries.listMyRunsForUser, {
			userId,
			limit: args.limit
		});
	}
});

export const getRunSummary = createTool({
	description:
		'Get high-level metadata for a simulation run (scenario, status, last tick). ' +
		'Includes scenarioConfig — the resolved YAML (climate baseline, driver kinds + ' +
		'params, maintenance schedule). Use scenarioConfig to explain *why* a run aged ' +
		'the way it did, not just what happened. Always cite the runId in your answer.',
	args: z.object({
		runId: z.string().describe('Convex run ID (an Id<"simRuns">)')
	}),
	handler: async (ctx, args): Promise<unknown> => {
		const userId = requireUserId(ctx);
		return await ctx.runQuery(internal.sim.queries.getRunSummaryForUser, {
			userId,
			runId: args.runId as Id<'simRuns'>
		});
	}
});

export const getStateAtTick = createTool({
	description:
		'Read the full printer state at a specific tick of a simulation run: drivers, ' +
		'environment, all 6 component health indices + statuses (true and observed), ' +
		'coupling factors, and print outcome. Cite runId AND tick AND componentId in your answer.',
	args: z.object({
		runId: z.string(),
		tick: z.number().int().nonnegative()
	}),
	handler: async (ctx, args): Promise<unknown> => {
		const userId = requireUserId(ctx);
		return await ctx.runQuery(internal.sim.queries.getStateAtTickForUser, {
			userId,
			runId: args.runId as Id<'simRuns'>,
			tick: args.tick
		});
	}
});

export const getComponentTimeseries = createTool({
	description:
		'Read the per-tick health series for one component (blade, rail, nozzle, cleaning, ' +
		'heater, sensor) over an optional [fromTick, toTick] window. Use this to find when ' +
		'a component first crossed DEGRADED/CRITICAL/FAILED.',
	args: z.object({
		runId: z.string(),
		componentId: componentSchema,
		fromTick: z.number().int().nonnegative().optional(),
		toTick: z.number().int().nonnegative().optional()
	}),
	handler: async (ctx, args): Promise<unknown> => {
		const userId = requireUserId(ctx);
		return await ctx.runQuery(internal.sim.queries.getComponentTimeseriesForUser, {
			userId,
			runId: args.runId as Id<'simRuns'>,
			componentId: args.componentId,
			fromTick: args.fromTick,
			toTick: args.toTick
		});
	}
});

export const getMultiComponentTimeseries = createTool({
	description:
		'Read per-tick health for MULTIPLE components in a single call. Returns wide rows ' +
		'shaped { tick, blade?, rail?, nozzle?, cleaning?, heater?, sensor? } where each ' +
		'componentId key is the healthIndex for that component at that tick (null if absent). ' +
		'Prefer this over multiple getComponentTimeseries calls when the user wants a chart ' +
		'spanning more than one component — the wide shape drops directly into LineChart data ' +
		'with one series entry per componentId.',
	args: z.object({
		runId: z.string(),
		componentIds: z.array(componentSchema).min(1),
		fromTick: z.number().int().nonnegative().optional(),
		toTick: z.number().int().nonnegative().optional()
	}),
	handler: async (ctx, args): Promise<unknown> => {
		const userId = requireUserId(ctx);
		return await ctx.runQuery(internal.sim.queries.getMultiComponentTimeseriesForUser, {
			userId,
			runId: args.runId as Id<'simRuns'>,
			componentIds: args.componentIds,
			fromTick: args.fromTick,
			toTick: args.toTick
		});
	}
});

export const listEvents = createTool({
	description:
		'List operator/maintenance events (TROUBLESHOOT, FIX, REPLACE) for a run, optionally ' +
		'filtered by tick range. Use this to explain what the operator did and when.',
	args: z.object({
		runId: z.string(),
		fromTick: z.number().int().nonnegative().optional(),
		toTick: z.number().int().nonnegative().optional(),
		limit: z.number().int().positive().max(500).optional()
	}),
	handler: async (ctx, args): Promise<unknown> => {
		const userId = requireUserId(ctx);
		return await ctx.runQuery(internal.sim.queries.listEventsForUser, {
			userId,
			runId: args.runId as Id<'simRuns'>,
			fromTick: args.fromTick,
			toTick: args.toTick,
			limit: args.limit
		});
	}
});

export const inspectSensorTrust = createTool({
	description:
		'For a component, return per-tick true health vs observed health vs sensor note. ' +
		'Use this to distinguish a real component fault from a sensor fault: a large ' +
		'true-vs-observed gap with a sensor_note like "drift" or "stuck" means the sensor ' +
		'is misleading the operator.',
	args: z.object({
		runId: z.string(),
		componentId: componentSchema,
		fromTick: z.number().int().nonnegative().optional(),
		toTick: z.number().int().nonnegative().optional()
	}),
	handler: async (ctx, args): Promise<unknown> => {
		const userId = requireUserId(ctx);
		return await ctx.runQuery(internal.sim.queries.inspectSensorTrustForUser, {
			userId,
			runId: args.runId as Id<'simRuns'>,
			componentId: args.componentId,
			fromTick: args.fromTick,
			toTick: args.toTick
		});
	}
});

export const compareRuns = createTool({
	description:
		'Compare the final-tick health of one component across two runs. Use this to answer ' +
		'what-if questions: "did the heater hold up better in Phoenix vs Barcelona?"',
	args: z.object({
		runIdA: z.string(),
		runIdB: z.string(),
		componentId: componentSchema
	}),
	handler: async (ctx, args): Promise<unknown> => {
		const userId = requireUserId(ctx);
		return await ctx.runQuery(internal.sim.queries.compareRunsForUser, {
			userId,
			runIdA: args.runIdA as Id<'simRuns'>,
			runIdB: args.runIdB as Id<'simRuns'>,
			componentId: args.componentId
		});
	}
});

export const runScenario = createTool({
	description:
		'Spawn a new simulation run. The run is one-shot: it computes all ticks immediately ' +
		'and returns the new runId. If the user explicitly asked to run / spawn / do a ' +
		'scenario, call this immediately — sending the message IS their confirmation. ' +
		'Only ask "yes/no" first when YOU are proposing an unsolicited what-if the user ' +
		'did not request. When in doubt, run.',
	args: z.object({
		scenario: z
			.string()
			.describe('Scenario YAML name, e.g. "barcelona-baseline" or "phoenix-aggressive"'),
		seed: z.number().int().optional(),
		horizonTicks: z.number().int().positive().max(10000).optional(),
		dtSeconds: z.number().int().positive().optional()
	}),
	handler: async (ctx, args): Promise<unknown> => {
		const userId = requireUserId(ctx);
		return await ctx.runAction(internal.sim.actions.runScenarioForUser, {
			userId,
			...args
		});
	}
});
