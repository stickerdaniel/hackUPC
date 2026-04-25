/**
 * Agent tools for the printer simulator.
 *
 * Use `createTool` from `@convex-dev/agent` (NOT plain `tool()` from `ai`)
 * because handlers need Convex action `ctx` (`ctx.runQuery`, `ctx.runAction`).
 *
 * Read tools wrap `sim/queries.ts`; the single mutation tool wraps
 * `sim/actions.ts:runScenario`. Every read result includes `runId`/`tick`/
 * `componentId` so the agent can cite specific data points back to the user
 * (Phase 3 grounding protocol — never answer printer state from training).
 */
import { createTool } from '@convex-dev/agent';
import { z } from 'zod';
import { api } from '../_generated/api';
import type { Id } from '../_generated/dataModel';

const componentSchema = z.enum(['blade', 'rail', 'nozzle', 'cleaning', 'heater', 'sensor']);

export const getRunSummary = createTool({
	description:
		'Get high-level metadata for a simulation run (scenario, status, last tick). ' +
		'Always cite the runId in your answer.',
	args: z.object({
		runId: z.string().describe('Convex run ID (an Id<"simRuns">)')
	}),
	handler: async (ctx, args): Promise<unknown> => {
		return await ctx.runQuery(api.sim.queries.getRunSummary, {
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
		return await ctx.runQuery(api.sim.queries.getStateAtTick, {
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
		return await ctx.runQuery(api.sim.queries.getComponentTimeseries, {
			runId: args.runId as Id<'simRuns'>,
			componentId: args.componentId,
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
		return await ctx.runQuery(api.sim.queries.listEvents, {
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
		return await ctx.runQuery(api.sim.queries.inspectSensorTrust, {
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
		return await ctx.runQuery(api.sim.queries.compareRuns, {
			runIdA: args.runIdA as Id<'simRuns'>,
			runIdB: args.runIdB as Id<'simRuns'>,
			componentId: args.componentId
		});
	}
});

// Mutation tool registered in step 10. Defining here keeps tool registration
// in one place; the agent's instructions decide whether/when to invoke it.
export const runScenario = createTool({
	description:
		'Spawn a new simulation run for what-if analysis. ALWAYS show the user the proposed ' +
		'config (scenario name, seed, horizonTicks) and ask for confirmation before calling ' +
		'this. The run is one-shot: it computes all ticks immediately and returns the new ' +
		'runId. Never call this without explicit user confirmation.',
	args: z.object({
		scenario: z
			.string()
			.describe('Scenario YAML name, e.g. "barcelona-baseline" or "phoenix-aggressive"'),
		seed: z.number().int().optional(),
		horizonTicks: z.number().int().positive().max(10000).optional(),
		dtSeconds: z.number().int().positive().optional()
	}),
	handler: async (ctx, args): Promise<unknown> => {
		return await ctx.runAction(api.sim.actions.runScenario, args);
	}
});
