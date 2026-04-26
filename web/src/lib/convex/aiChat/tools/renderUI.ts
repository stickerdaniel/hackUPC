import { tool } from 'ai';
import { z } from 'zod';
import { chatCatalog } from '../../../render/catalog';

/**
 * Tool the LLM calls AFTER fetching data via other tools, with a json-render
 * spec describing the UI to render inline in the chat. Validation runs in two
 * passes:
 *  1. chatCatalog.validate(spec) checks shape + that every element.type is a
 *     real catalog component.
 *  2. Per-element prop parse — pass 1's prop check degrades to z.record(...)
 *     for multi-component catalogs (see core/src/schema.ts:520-531), so we
 *     redo prop validation against the per-component Zod schema.
 *
 * Missing-but-nullable props are filled with null before pass 2 — the shadcn
 * catalog uses z.string().nullable() (key required, value can be null) but
 * the runtime renderer is permissive (Card.svelte:25-32 just checks `if
 * (props.title)`), so the LLM tends to omit them entirely. Filling bridges
 * the gap without rewriting the upstream catalog.
 *
 * Returns the original parsed spec on success — NOT shape.data — because the
 * Svelte schema's spec object only declares { root, elements }
 * (svelte/src/schema.ts:13-29) and z.object().parse() would strip any
 * top-level { state: {...} } the LLM included, breaking $state bindings.
 */
export const renderUI = tool({
	description:
		'Render a UI for the user from a json-render spec. Call this AFTER ' +
		'fetching data via other tools. The spec must use only components from ' +
		'the shadcn catalog (Card, Stack, Grid, Heading, Text, Badge, Table, ' +
		'Alert, Separator, Progress, Button, LineChart, BarChart, etc.).',
	inputSchema: z.object({
		spec: z.string().describe('json-render spec as a JSON string')
	}),
	execute: async ({ spec }) => {
		let parsed: unknown;
		try {
			parsed = JSON.parse(spec);
		} catch (e) {
			return { ok: false as const, error: `Invalid JSON: ${(e as Error).message}` };
		}

		// Fill `children: []` on any element missing it. The svelte spec schema
		// requires `children: z.array(z.string())` on every element (see
		// references/json-render/packages/svelte/src/schema.ts:24), but the
		// shadcn catalog only marks containers (Card, Stack, Grid, Tabs,
		// Collapsible, Dialog, Drawer) with `slots: ["default"]`, so smaller
		// LLMs reasonably omit `children` on leaf components like Heading,
		// Text, Badge, Table, Separator. Backfilling here turns those silent
		// shape errors into successful renders.
		const rawElements = (parsed as { elements?: Record<string, unknown> }).elements;
		if (rawElements && typeof rawElements === 'object') {
			for (const el of Object.values(rawElements)) {
				if (el && typeof el === 'object' && !('children' in el)) {
					(el as { children: string[] }).children = [];
				}
			}
		}

		const shape = chatCatalog.validate(parsed);
		if (!shape.success) {
			const msg = shape.error?.message ?? 'unknown validation error';
			return { ok: false as const, error: `Spec shape invalid: ${msg}` };
		}

		const components = (chatCatalog as any).data?.components ?? {};
		const elements =
			(parsed as { elements?: Record<string, { type: string; props?: unknown }> }).elements ?? {};

		for (const [key, el] of Object.entries(elements)) {
			const def = components[el.type];
			if (!def) {
				return {
					ok: false as const,
					error: `Element "${key}": unknown component "${el.type}"`
				};
			}
			const filledProps = fillMissingNullableProps(
				(el.props as Record<string, unknown> | undefined) ?? {},
				def.props as z.ZodObject
			);
			const propResult = (def.props as z.ZodTypeAny).safeParse(filledProps);
			if (!propResult.success) {
				return {
					ok: false as const,
					error: `Element "${key}" (${el.type}): ${propResult.error.message}`
				};
			}
			(el as { props?: unknown }).props = propResult.data;
		}

		return { ok: true as const, spec: parsed };
	}
});

/**
 * Fill in missing nullable keys with null so strict z.object().safeParse()
 * accepts the LLM's permissive output. Detects "nullable" by probing the
 * field schema with safeParse(null) — works for both .nullable() and
 * .nullish() without depending on Zod-internal type names.
 */
function fillMissingNullableProps(
	props: Record<string, unknown>,
	schema: z.ZodObject
): Record<string, unknown> {
	const out: Record<string, unknown> = { ...props };
	const shape = schema.shape as Record<string, z.ZodTypeAny>;
	for (const [key, fieldSchema] of Object.entries(shape)) {
		if (out[key] === undefined && fieldSchema.safeParse(null).success) {
			out[key] = null;
		}
	}
	return out;
}
