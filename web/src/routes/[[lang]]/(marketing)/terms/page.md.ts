import type { MarketingMarkdownDocument } from '$lib/markdown/types';

export const marketingMarkdown: MarketingMarkdownDocument = {
	title: 'Terms of Service',
	description: 'The terms and conditions for using Co-Pilot.',
	sections: [
		{
			heading: 'Terms of Service',
			paragraphs: [
				'By accessing or using Co-Pilot you agree to be bound by these Terms of Service.',
				'Co-Pilot is a digital twin and AI maintenance copilot for the HP Metal Jet S100, provided by Daniel Sticker as a personal project.',
				'You are responsible for maintaining the confidentiality of your account credentials.',
				'The Service is provided "as is" without warranties of any kind.',
				'These Terms are governed by the laws of the Federal Republic of Germany.'
			]
		}
	]
};
