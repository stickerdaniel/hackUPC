import { schema } from '@json-render/svelte/schema';
import { shadcnComponentDefinitions } from '@json-render/shadcn-svelte/catalog';

export const chatCatalog = schema.createCatalog({
	components: shadcnComponentDefinitions,
	actions: {}
});
