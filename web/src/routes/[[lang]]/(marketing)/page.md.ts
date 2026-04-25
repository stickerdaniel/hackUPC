import type { MarketingMarkdownDocument } from '$lib/markdown/types';

export const marketingMarkdown: MarketingMarkdownDocument = {
	title: 'Build & Ship Your Product Faster',
	description:
		'The free SaaS foundation. An open-source SvelteKit starter with auth, billing, email, and analytics. Deploy on free tiers, own every line.',
	sections: [
		{
			heading: 'What this starter is',
			paragraphs: [
				'Co-Pilot is a digital twin and AI maintenance copilot for the HP Metal Jet S100 industrial 3D printer.',
				'It is designed for founders and product teams who want to focus on product differentiation rather than rebuilding authentication, billing, localization, and operational plumbing.'
			]
		},
		{
			heading: 'Why teams use it',
			bullets: [
				'Launch faster with a ready-made SaaS foundation',
				'Keep a modern SvelteKit architecture with typed backend integrations',
				'Start from real product workflows instead of a blank UI kit',
				'Own the full codebase with an open-source template'
			]
		},
		{
			heading: 'Key integrations',
			links: [
				{
					label: 'Svelte 5',
					href: 'https://svelte.dev',
					description: 'Frontend framework for the application shell and marketing site'
				},
				{
					label: 'Convex',
					href: 'https://convex.dev',
					description: 'Realtime backend, database, and server functions'
				},
				{
					label: 'Better Auth',
					href: 'https://www.better-auth.com/',
					description: 'Authentication, sessions, OAuth, and passkeys'
				},
				{
					label: 'Tolgee',
					href: 'https://tolgee.io',
					description: 'Localization and translation workflow'
				},
				{
					label: 'PostHog',
					href: 'https://posthog.com/',
					description: 'Product analytics and conversion tracking'
				},
				{
					label: 'Resend',
					href: 'https://resend.com',
					description: 'Transactional email delivery'
				}
			]
		},
		{
			heading: 'Primary call to action',
			paragraphs: ['The primary action on the page is sign-up for the starter experience.'],
			links: [
				{
					label: 'Start building',
					href: '/en/signup',
					description: 'Create an account and enter the product flow'
				}
			]
		}
	]
};
