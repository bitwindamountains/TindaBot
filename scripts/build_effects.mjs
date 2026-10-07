import {build} from 'esbuild';
import {mkdirSync, readFileSync, writeFileSync, existsSync} from 'node:fs';
const outdir = 'src/tindabot/web/effects';
mkdirSync(outdir, {recursive: true});
await build({entryPoints: ['frontend/hero.jsx'], outfile: `${outdir}/hero.js`, bundle: true,
  minify: true, format: 'esm', target: ['es2022'], legalComments: 'linked',
  define: {'process.env.NODE_ENV': '"production"'}, logLevel: 'info'});
const names = ['react', 'react-dom', '@react-three/fiber', '@shadergradient/react', 'three', 'three-stdlib', 'camera-controls'];
writeFileSync(`${outdir}/THIRD_PARTY_NOTICES.txt`, names.map(name => {
  const dir = `node_modules/${name}`;
  const pkg = JSON.parse(readFileSync(`${dir}/package.json`, 'utf8'));
  const license = ['LICENSE', 'LICENSE.md', 'LICENSE.txt'].find(file => existsSync(`${dir}/${file}`));
  return `${name} ${pkg.version}\n${license ? readFileSync(`${dir}/${license}`, 'utf8') : `License: ${pkg.license}. See upstream repository.`}`;
}).join('\n\n--------------------\n\n'));
