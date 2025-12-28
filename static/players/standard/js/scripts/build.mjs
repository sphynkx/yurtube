import * as esbuild from 'esbuild';
import { fileURLToPath } from 'url';
import { dirname, resolve } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const ROOT = resolve(__dirname, '..');

const isWatch = process.argv.includes('--watch');
const isProd = process.argv.includes('--prod') || process.env.NODE_ENV === 'production';
const onlyEmbed = process.argv.includes('--target=embed');
const onlyPlayer = process.argv.includes('--target=player');

const baseOptions = {
  bundle: true,
  minify: isProd,
  sourcemap: !isProd,
  target: ['es2018'],
  format: 'iife',
  legalComments: 'none',
  logLevel: 'info',
  drop: isProd ? ['console', 'debugger'] : []
};

async function buildOne(entry, outfile) {
  const options = { ...baseOptions, entryPoints: [entry], outfile };
  if (isWatch) {
    const ctx = await esbuild.context(options);
    await ctx.watch();
    console.log('Watching:', outfile);
    return ctx;
  } else {
    await esbuild.build(options);
    console.log('Built:', outfile, `(prod=${isProd ? 'yes' : 'no'})`);
    return null;
  }
}

const entryPlayer = resolve(ROOT, 'src/player.entry.js');
const outPlayer = resolve(ROOT, 'player.js');
const entryEmbed = resolve(ROOT, 'src/embed.entry.js');
const outEmbed = resolve(ROOT, 'embed.js');

try {
  let ctxs = [];
  if (onlyEmbed) {
    const c = await buildOne(entryEmbed, outEmbed); if (c) ctxs.push(c);
  } else if (onlyPlayer) {
    const c = await buildOne(entryPlayer, outPlayer); if (c) ctxs.push(c);
  } else {
    const c1 = await buildOne(entryPlayer, outPlayer);
    const c2 = await buildOne(entryEmbed, outEmbed);
    if (c1) ctxs.push(c1);
    if (c2) ctxs.push(c2);
  }
  if (!isWatch) process.exit(0);
} catch (e) {
  console.error('Build failed:', e);
  process.exit(1);
}