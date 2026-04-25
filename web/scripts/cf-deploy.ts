/**
 * CF Workers deploy command — wraps `wrangler versions upload` with preview alias support.
 *
 * For preview branches, passes --preview-alias with a sanitized branch name
 * so CF Workers creates a valid alias even for branches starting with digits.
 *
 * Set as the non-production deploy command in CF Workers Builds dashboard.
 */

import { spawnSync } from 'child_process';
import { sanitizeBranchAlias } from './deploy/platform';

const branch = process.env.WORKERS_CI_BRANCH;
const productionBranch = process.env.PRODUCTION_BRANCH || 'main';
const isPreview = branch !== undefined && branch !== productionBranch;

const args = ['wrangler', 'versions', 'upload'];

if (isPreview && branch) {
	const alias = sanitizeBranchAlias(branch);
	args.push('--preview-alias', alias);
	console.log(`Preview alias: ${alias}`);
}

const result = spawnSync('bunx', args, { stdio: 'inherit' });

// On successful production deploys, purge the CF cache so the custom domain
// doesn't serve stale HTML. Skipped for previews and when env is not configured.
if (result.status === 0 && !isPreview) {
	const zoneId = process.env.CF_ZONE_ID;
	const apiToken = process.env.CLOUDFLARE_API_TOKEN;
	if (zoneId && apiToken) {
		console.log('Purging Cloudflare cache...');
		const purge = spawnSync(
			'curl',
			[
				'-fsS',
				'-X',
				'POST',
				`https://api.cloudflare.com/client/v4/zones/${zoneId}/purge_cache`,
				'-H',
				`Authorization: Bearer ${apiToken}`,
				'-H',
				'Content-Type: application/json',
				'-d',
				'{"purge_everything":true}'
			],
			{ stdio: 'inherit' }
		);
		if (purge.status !== 0) {
			console.warn('Cache purge failed (non-fatal, deploy already succeeded)');
		}
	} else {
		console.warn('Skipping cache purge: CF_ZONE_ID or CLOUDFLARE_API_TOKEN not set');
	}
}

process.exit(result.status ?? 1);
