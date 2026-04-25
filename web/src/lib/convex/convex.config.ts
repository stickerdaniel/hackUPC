import { defineApp } from 'convex/server';
import betterAuth from './betterAuth/convex.config';
import resend from '@convex-dev/resend/convex.config';
import agent from '@convex-dev/agent/convex.config';
import rateLimiter from '@convex-dev/rate-limiter/convex.config';
import convexFilesControl from '@gilhrpenner/convex-files-control/convex.config';

const app = defineApp();
app.use(betterAuth);
app.use(resend);
app.use(agent);
app.use(rateLimiter);
app.use(convexFilesControl);

export default app;
