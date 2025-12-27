import * as esbuild from 'esbuild';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const ROOT = resolve(__dirname, '..');

const entry = resolve(ROOT, 'src/player.entry.js');
const outfile = resolve(ROOT, 'player.js');

const isWatch = process.argv.includes('--watch');
const isProd = process.argv.includes('--prod') || process.env.NODE_ENV === 'production';

const options = {
  entryPoints: [entry],
  outfile,
  bundle: true,
  minify: isProd,
  sourcemap: !isProd,
  target: ['es2018'],
  format: 'iife',
  globalName: 'YRPBundle',
  legalComments: 'none',
  logLevel: 'info',
  drop: isProd ? ['console', 'debugger'] : []
};

try {
  if (isWatch) {
    const ctx = await esbuild.context(options);
    await ctx.watch();
    console.log('Watching for changes…');
  } else {
    await esbuild.build(options);
    console.log('Built:', outfile, `(prod=${isProd ? 'yes' : 'no'})`);
  }
} catch (e) {
  console.error('Build failed:', e);
  process.exit(1);
}