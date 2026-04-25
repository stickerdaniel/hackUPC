import { defineRegistry } from '@json-render/svelte';
import { shadcnComponents } from '@json-render/shadcn-svelte';
import { chatCatalog } from './catalog';

export const { registry } = defineRegistry(chatCatalog, {
	components: shadcnComponents
});
