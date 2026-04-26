import { schema } from '@json-render/svelte/schema';
import { shadcnComponentDefinitions } from '@json-render/shadcn-svelte/catalog';
import { z } from 'zod';

export const chatCatalog = schema.createCatalog({
	components: {
		...shadcnComponentDefinitions,

		LineChart: {
			props: z.object({
				title: z.string().nullable(),
				description: z.string().nullable(),
				data: z.array(z.record(z.string(), z.unknown())),
				xKey: z.string(),
				series: z.array(
					z.object({
						key: z.string(),
						label: z.string(),
						color: z.string().nullable()
					})
				),
				yMin: z.number().nullable(),
				yMax: z.number().nullable(),
				events: z
					.array(
						z.object({
							tick: z.number(),
							label: z.string(),
							color: z.string().nullable()
						})
					)
					.nullable(),
				height: z.number().nullable()
			}),
			description:
				'Time-series line chart. Multi-series via series[]. Use for healthIndex over ticks, sensor trueHealth vs observedHealth, etc. data is an array of flat {[xKey], ...seriesKeys} rows. events are optional vertical-rule annotations at specific x ticks.',
			example: {
				title: 'Blade health',
				description: null,
				data: [
					{ tick: 0, healthIndex: 1.0 },
					{ tick: 50, healthIndex: 0.78 },
					{ tick: 100, healthIndex: 0.42 }
				],
				xKey: 'tick',
				series: [{ key: 'healthIndex', label: 'Blade', color: '#6366f1' }],
				yMin: 0,
				yMax: 1,
				events: null,
				height: 240
			}
		},

		BarChart: {
			props: z.object({
				title: z.string().nullable(),
				description: z.string().nullable(),
				data: z.array(z.record(z.string(), z.unknown())),
				xKey: z.string(),
				yKey: z.string(),
				color: z.string().nullable(),
				height: z.number().nullable()
			}),
			description:
				'Categorical bar chart. Use for compareRuns final-tick scores or event counts per component. data is an array of {[xKey]: string, [yKey]: number} rows.',
			example: {
				title: 'Final blade health',
				description: null,
				data: [
					{ run: 'barcelona', health: 0.62 },
					{ run: 'phoenix', health: 0.34 }
				],
				xKey: 'run',
				yKey: 'health',
				color: '#6366f1',
				height: 240
			}
		}
	},
	actions: {}
});
