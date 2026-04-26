import { defineRegistry } from '@json-render/svelte';
import { shadcnComponents } from '@json-render/shadcn-svelte';
import { chatCatalog } from './catalog';
import LineChart from './charts/LineChart.svelte';
import BarChart from './charts/BarChart.svelte';

export const { registry } = defineRegistry(chatCatalog, {
	components: { ...shadcnComponents, LineChart, BarChart }
});
